import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import SaaSPlanModel
from api.services.auth.depends import get_superuser

router = APIRouter(prefix="/plans", tags=["admin-plans"])


class PlanItem(BaseModel):
    id: Optional[str] = None
    name: str
    code: str
    description: Optional[str] = None
    monthly_price_cents: int = 0
    monthly_price_inr: float = 0.0
    monthly_price_usd: float = 0.0
    annual_price_cents: int = 0
    currency: str = "INR"
    included_monthly_minutes: int = 60
    included_minutes: int = 60
    overage_rate_per_minute: float = 0.0
    max_agents: int = 3
    max_concurrent_calls: int = 2
    has_crm_access: bool = True
    has_appointments_access: bool = True
    has_forms_access: bool = True
    has_widget_access: bool = True
    allow_user_byok: bool = False
    is_default: bool = False
    is_active: bool = True
    is_public: bool = True


@router.get("", response_model=List[PlanItem])
async def list_plans(_user=Depends(get_superuser)):
    """List all SaaS subscription plans."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(SaaSPlanModel).order_by(SaaSPlanModel.monthly_price_cents)
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [
            PlanItem(
                id=str(r.id),
                name=r.name,
                code=r.code,
                description=r.description,
                monthly_price_cents=r.monthly_price_cents,
                monthly_price_inr=float(r.monthly_price_cents / 100.0) if r.currency == "INR" else float(r.monthly_price_cents * 0.83),
                monthly_price_usd=float(r.monthly_price_cents / 100.0) if r.currency == "USD" else float(r.monthly_price_cents / 8300.0),
                annual_price_cents=r.annual_price_cents,
                currency=r.currency,
                included_monthly_minutes=r.included_monthly_minutes,
                included_minutes=r.included_monthly_minutes,
                max_agents=r.max_agents,
                max_concurrent_calls=r.max_concurrent_calls,
                has_crm_access=r.has_crm_access,
                has_appointments_access=r.has_appointments_access,
                has_forms_access=r.has_forms_access,
                has_widget_access=r.has_widget_access,
                allow_user_byok=r.allow_user_byok,
                is_default=r.is_default,
                is_active=r.is_active,
                is_public=True,
            )
            for r in records
        ]


@router.post("", response_model=Dict[str, Any])
async def upsert_plan(plan: PlanItem, _user=Depends(get_superuser)):
    """Create or upsert a SaaS plan."""
    cents = plan.monthly_price_cents
    if cents == 0 and plan.monthly_price_inr > 0:
        cents = int(plan.monthly_price_inr * 100)
    minutes = plan.included_minutes if plan.included_minutes > 0 else plan.included_monthly_minutes

    async with kodewaves_db_client.get_session() as session:
        stmt = select(SaaSPlanModel).where(SaaSPlanModel.code == plan.code)
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        if record:
            record.name = plan.name
            record.description = plan.description
            record.monthly_price_cents = cents
            record.annual_price_cents = plan.annual_price_cents or (cents * 10)
            record.currency = plan.currency
            record.included_monthly_minutes = minutes
            record.max_agents = plan.max_agents
            record.max_concurrent_calls = plan.max_concurrent_calls
            record.has_crm_access = plan.has_crm_access
            record.has_appointments_access = plan.has_appointments_access
            record.has_forms_access = plan.has_forms_access
            record.has_widget_access = plan.has_widget_access
            record.allow_user_byok = plan.allow_user_byok
            record.is_default = plan.is_default
            record.is_active = plan.is_active
        else:
            record = SaaSPlanModel(
                name=plan.name,
                code=plan.code,
                description=plan.description,
                monthly_price_cents=cents,
                annual_price_cents=plan.annual_price_cents or (cents * 10),
                currency=plan.currency,
                included_monthly_minutes=minutes,
                max_agents=plan.max_agents,
                max_concurrent_calls=plan.max_concurrent_calls,
                has_crm_access=plan.has_crm_access,
                has_appointments_access=plan.has_appointments_access,
                has_forms_access=plan.has_forms_access,
                has_widget_access=plan.has_widget_access,
                allow_user_byok=plan.allow_user_byok,
                is_default=plan.is_default,
                is_active=plan.is_active,
            )
            session.add(record)

        await session.commit()
        return {"message": f"Successfully configured plan '{plan.name}'", "id": str(record.id)}


@router.put("/{plan_id}", response_model=Dict[str, Any])
async def update_plan(plan_id: str, plan: PlanItem, _user=Depends(get_superuser)):
    """Update an existing SaaS plan by ID or code."""
    cents = plan.monthly_price_cents
    if cents == 0 and plan.monthly_price_inr > 0:
        cents = int(plan.monthly_price_inr * 100)
    minutes = plan.included_minutes if plan.included_minutes > 0 else plan.included_monthly_minutes

    async with kodewaves_db_client.get_session() as session:
        try:
            p_uuid = uuid.UUID(plan_id)
            stmt = select(SaaSPlanModel).where(SaaSPlanModel.id == p_uuid)
        except ValueError:
            stmt = select(SaaSPlanModel).where(SaaSPlanModel.code == plan_id)

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="SaaS Plan not found")

        record.name = plan.name
        record.description = plan.description
        record.monthly_price_cents = cents
        record.annual_price_cents = plan.annual_price_cents or (cents * 10)
        record.currency = plan.currency
        record.included_monthly_minutes = minutes
        record.max_agents = plan.max_agents
        record.max_concurrent_calls = plan.max_concurrent_calls
        record.has_crm_access = plan.has_crm_access
        record.has_appointments_access = plan.has_appointments_access
        record.has_forms_access = plan.has_forms_access
        record.has_widget_access = plan.has_widget_access
        record.allow_user_byok = plan.allow_user_byok
        record.is_default = plan.is_default
        record.is_active = plan.is_active

        await session.commit()
        return {"message": f"Successfully updated plan '{record.name}'", "id": str(record.id)}


@router.delete("/{plan_id}", response_model=Dict[str, Any])
async def delete_plan(plan_id: str, _user=Depends(get_superuser)):
    """Delete a SaaS plan by ID or code."""
    async with kodewaves_db_client.get_session() as session:
        try:
            p_uuid = uuid.UUID(plan_id)
            stmt = select(SaaSPlanModel).where(SaaSPlanModel.id == p_uuid)
        except ValueError:
            stmt = select(SaaSPlanModel).where(SaaSPlanModel.code == plan_id)

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="SaaS Plan not found")

        await session.delete(record)
        await session.commit()
        return {"message": f"Successfully deleted plan '{record.name}'"}
