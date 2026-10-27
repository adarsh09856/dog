"""Client administrator workspace operations under signed installation limits."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, text

from api.db import db_client
from api.db.kodewaves_models import GlobalPlatformSettingModel
from api.db.models import (
    OrganizationModel,
    UserModel,
    organization_users_association,
)
from api.services.client_creation_limits import enforce_client_creation_limit


async def list_admin_workspaces(administrator_id: int) -> list[dict]:
    async with db_client.async_session() as session:
        result = await session.execute(
            select(OrganizationModel)
            .join(
                organization_users_association,
                organization_users_association.c.organization_id == OrganizationModel.id,
            )
            .where(organization_users_association.c.user_id == administrator_id)
            .order_by(OrganizationModel.id)
        )
        organizations = result.scalars().all()
        if not organizations:
            return []
        settings = await session.execute(
            select(GlobalPlatformSettingModel).where(
                GlobalPlatformSettingModel.key.in_(
                    [f"org_name_{organization.id}" for organization in organizations]
                )
            )
        )
        names = {item.key: item.value.get("name") for item in settings.scalars().all()}
        return [
            {
                "id": organization.id,
                "name": names.get(f"org_name_{organization.id}") or f"Workspace {organization.id}",
            }
            for organization in organizations
        ]


async def create_admin_workspace(administrator_id: int, name: str) -> int:
    async with db_client.async_session() as session, session.begin():
        await session.execute(text("SELECT pg_advisory_xact_lock(492565710843)"))
        await enforce_client_creation_limit(
            session, limit_name="max_workspaces", model=OrganizationModel
        )
        organization = OrganizationModel(
            provider_id=f"client_{uuid.uuid4()}", created_at=datetime.now(UTC)
        )
        session.add(organization)
        await session.flush()
        await session.execute(
            organization_users_association.insert().values(
                user_id=administrator_id, organization_id=organization.id
            )
        )
        administrator = await session.get(UserModel, administrator_id, with_for_update=True)
        if administrator is None or not administrator.is_superuser:
            raise HTTPException(status_code=403, detail="Client administrator access required")
        administrator.selected_organization_id = organization.id
        session.add(GlobalPlatformSettingModel(
            key=f"org_name_{organization.id}",
            value={"name": name},
            category="organization",
        ))
        return organization.id


async def switch_admin_workspace(administrator_id: int, organization_id: int) -> None:
    async with db_client.async_session() as session, session.begin():
        member = await session.scalar(
            select(organization_users_association.c.user_id).where(
                organization_users_association.c.user_id == administrator_id,
                organization_users_association.c.organization_id == organization_id,
            )
        )
        if member is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        administrator = await session.get(UserModel, administrator_id, with_for_update=True)
        if administrator is None or not administrator.is_superuser:
            raise HTTPException(status_code=403, detail="Client administrator access required")
        administrator.selected_organization_id = organization_id
