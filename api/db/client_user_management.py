"""Client administrator user operations scoped to one workspace."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select, text

from api.db import db_client
from api.db.models import UserModel, organization_users_association
from api.services.client_creation_limits import enforce_client_creation_limit
from api.utils.auth import hash_password


async def list_workspace_users(organization_id: int) -> list[UserModel]:
    async with db_client.async_session() as session:
        result = await session.execute(
            select(UserModel)
            .join(
                organization_users_association,
                organization_users_association.c.user_id == UserModel.id,
            )
            .where(organization_users_association.c.organization_id == organization_id)
            .order_by(UserModel.id)
        )
        return list(result.scalars().all())


async def create_workspace_user(organization_id: int, email: str, password: str) -> UserModel:
    normalized_email = email.strip().lower()
    password_hash = hash_password(password)
    async with db_client.async_session() as session, session.begin():
        await session.execute(text("SELECT pg_advisory_xact_lock(492565710843)"))
        duplicate = await session.scalar(
            select(UserModel.id).where(func.lower(UserModel.email) == normalized_email)
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="Email already registered")
        await enforce_client_creation_limit(session, limit_name="max_seats", model=UserModel)
        user = UserModel(
            provider_id=f"oss_{int(datetime.now(UTC).timestamp())}_{uuid.uuid4()}",
            email=normalized_email,
            password_hash=password_hash,
            is_superuser=False,
            is_active=True,
            selected_organization_id=organization_id,
        )
        session.add(user)
        await session.flush()
        await session.execute(
            organization_users_association.insert().values(
                user_id=user.id, organization_id=organization_id
            )
        )
        user_id = user.id
    return await db_client.get_user_by_id(user_id)


async def set_workspace_user_active(
    organization_id: int, user_id: int, *, active: bool
) -> UserModel:
    async with db_client.async_session() as session, session.begin():
        user = await session.scalar(
            select(UserModel)
            .join(
                organization_users_association,
                organization_users_association.c.user_id == UserModel.id,
            )
            .where(
                organization_users_association.c.organization_id == organization_id,
                UserModel.id == user_id,
            )
            .with_for_update()
        )
        if user is None:
            raise HTTPException(status_code=404, detail="User not found in this workspace")
        if user.is_superuser:
            raise HTTPException(status_code=403, detail="Client administrator status cannot be changed here")
        memberships = await session.scalar(
            select(func.count())
            .select_from(organization_users_association)
            .where(organization_users_association.c.user_id == user_id)
        )
        if memberships != 1:
            raise HTTPException(
                status_code=409,
                detail="This account belongs to multiple workspaces and cannot be suspended here",
            )
        user.is_active = active
    return await db_client.get_user_by_id(user_id)
