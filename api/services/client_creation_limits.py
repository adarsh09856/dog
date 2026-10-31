"""Enforce signed installation resource caps when records are created."""

from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from api.constants import KODEWAVES_EDITION
from api.services.installation_license import (
    load_license,
    validate_installation_license,
)
from api.services.owner_installation_status import require_current_owner_status
from api.services.saas_entitlements import get_org_saas_limit


async def enforce_client_creation_limit(
    session: AsyncSession, *, limit_name: str, model: type, existing_query: Select | None = None
) -> Any | None:
    """Serialize counts and inserts across workers for a client installation.

    The caller must keep this transaction open until its new row is committed.
    An omitted signed limit means the owner has not set a cap for that resource.
    """
    if KODEWAVES_EDITION != "client":
        return None

    license_data = load_license()
    validate_installation_license(license_data)
    await require_current_owner_status(license_data)
    limit = license_data.limits.get(limit_name)
    if limit is None:
        return None

    # A transaction-scoped lock makes the count and insert one admission step.
    await session.execute(text("SELECT pg_advisory_xact_lock(492565710843)"))
    if existing_query is not None:
        existing = (await session.execute(existing_query)).scalars().first()
        if existing is not None:
            return existing
    current = (await session.execute(select(func.count(model.id)))).scalar_one()
    if current >= limit:
        raise HTTPException(status_code=403, detail=f"Installation {limit_name} limit reached")
    return None


async def enforce_saas_creation_limit(
    session: AsyncSession,
    *,
    organization_id: int | None,
    limit_name: str,
    model: type,
) -> None:
    """Apply the active SaaS plan's organization-scoped resource cap at insert time."""
    if KODEWAVES_EDITION == "client":
        return
    if organization_id is None:
        raise HTTPException(
            status_code=403,
            detail="Select an organization before creating an agent.",
        )
    limit = await get_org_saas_limit(organization_id, limit_name)
    if limit is None:
        return
    # Serialize count+insert for this organization so parallel creates cannot
    # overshoot the plan cap. The caller keeps this transaction open until commit.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(492565, :org_id)"),
        {"org_id": organization_id},
    )
    current = (
        await session.execute(
            select(func.count(model.id)).where(model.organization_id == organization_id)
        )
    ).scalar_one()
    if current >= int(limit):
        raise HTTPException(status_code=403, detail=f"Organization {limit_name} plan limit reached")
