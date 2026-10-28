"""Owner-managed SaaS catalog persistence and serialized default selection."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text, update

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import GlobalPlatformSettingModel, SaaSPlanModel


def _plan_selector(identifier: str):
    try:
        return SaaSPlanModel.id == uuid.UUID(identifier)
    except ValueError:
        return SaaSPlanModel.code == identifier


async def list_plans() -> list[SaaSPlanModel]:
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(SaaSPlanModel).order_by(SaaSPlanModel.monthly_price_cents, SaaSPlanModel.code)
        )
        return list(result.scalars().all())


async def save_plan(values: dict, *, identifier: str | None = None) -> SaaSPlanModel | None:
    """Upsert by code, or update an existing ID/code, choosing at most one default."""
    if values["is_default"] and not values["is_active"]:
        raise ValueError("The default plan must be active")
    async with kodewaves_db_client.get_session() as session:
        # Serialize all catalog mutations, including two simultaneous requests
        # choosing different defaults. Row locks alone miss newly inserted plans.
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": "kodewaves:saas-plan-catalog"},
        )
        selector = _plan_selector(identifier) if identifier is not None else SaaSPlanModel.code == values["code"]
        result = await session.execute(select(SaaSPlanModel).where(selector))
        record = result.scalar_one_or_none()
        if record is None and identifier is not None:
            return None
        if values["is_default"]:
            await session.execute(
                update(SaaSPlanModel).where(SaaSPlanModel.is_default.is_(True)).values(is_default=False)
            )
        if record is None:
            record = SaaSPlanModel(**values)
            session.add(record)
        else:
            for key, value in values.items():
                # Existing plan codes are stable references in organization
                # assignments and payment metadata; edits must preserve them.
                if key != "code":
                    setattr(record, key, value)
        await session.commit()
        await session.refresh(record)
        return record


async def delete_plan(identifier: str) -> str | None:
    async with kodewaves_db_client.get_session() as session:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": "kodewaves:saas-plan-catalog"},
        )
        result = await session.execute(select(SaaSPlanModel).where(_plan_selector(identifier)))
        record = result.scalar_one_or_none()
        if record is None:
            return None
        name = record.name
        await session.delete(record)
        await session.commit()
        return name


async def resolve_owner_plan(code: str | None, legacy_name: str | None = None):
    """Resolve a deliberate owner selection without guessing a code from a name."""
    if code is not None:
        plan = await kodewaves_db_client.get_active_saas_plan(code)
        if plan is None:
            raise ValueError("Select an active catalog plan")
        return plan
    if legacy_name is None:
        return None
    candidates = [p for p in await list_plans() if p.is_active and (
        p.code == legacy_name or p.name == legacy_name
    )]
    if len(candidates) != 1:
        raise ValueError("Plan name is unavailable or ambiguous; use its catalog code")
    return candidates[0]


async def assign_org_plan(organization_id: int, code: str) -> bool:
    """Change an owner grant without erasing a same-plan purchased term or minutes."""
    async with kodewaves_db_client.get_session() as session:
        # Match the payment-grant lock so checkout and an owner assignment cannot
        # overwrite each other's last committed term in parallel.
        await session.execute(text("SELECT pg_advisory_xact_lock(492566, :org_id)"), {"org_id": organization_id})
        result = await session.execute(select(SaaSPlanModel).where(
            SaaSPlanModel.code == code, SaaSPlanModel.is_active.is_(True),
        ))
        plan = result.scalar_one_or_none()
        if plan is None:
            raise ValueError("Select an active catalog plan")
        key = f"org_plan_{organization_id}"
        result = await session.execute(select(GlobalPlatformSettingModel).where(GlobalPlatformSettingModel.key == key))
        setting = result.scalar_one_or_none()
        previous = setting.value if setting is not None else None
        if isinstance(previous, dict) and previous.get("plan_code") == code:
            return False
        now = datetime.now(UTC)
        value = {"plan_code": code, "updated_at": now.isoformat(), "source": "owner_grant"}
        if plan.monthly_price_cents > 0 or plan.annual_price_cents > 0:
            value["expires_at"] = (now + timedelta(days=30)).isoformat()
        if setting is None:
            session.add(GlobalPlatformSettingModel(key=key, value=value, category="plan"))
        else:
            setting.value = value
            setting.updated_at = now
        await session.commit()
        return True
