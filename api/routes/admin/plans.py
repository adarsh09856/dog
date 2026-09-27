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
    annual_price_cents: int = 0
    currency: str = "INR"
    included_monthly_minutes: int = 60
    max_agents: int = 3
    max_concurrent_calls: int = 2
    has_crm_access: bool = True
    has_appointments_access: bool = True
    has_forms_access: bool = True
    has_widget_access: bool = True
    allow_user_byok: bool = False
    is_default: bool = False
    is_active: bool = True


@router.get("", response_model=List[PlanItem])
async def list_plans(_user=Depends(get_superuser)):
    """List all SaaS plans."""
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
                annual_price_cents=r.annual_price_cents,
                currency=r.currency,
                included_monthly_minutes=r.included_monthly_minutes,
                max_agents=r.max_agents,
                max_concurrent_calls=r.max_concurrent_calls,
                has_crm_access=r.has_crm_access,
                has_appointments_access=r.has_appointments_access,
                has_forms_access=r.has_forms_access,
                has_widget_access=r.has_widget_access,
                allow_user_byok=r.allow_user_byok,
                is_default=r.is_default,
                is_active=r.is_active,
            )
            for r in records
        ]


@router.post("", response_model=Dict[str, Any])
async def upsert_plan(plan: PlanItem, _user=Depends(get_superuser)):
    """Create or update a SaaS plan."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(SaaSPlanModel).where(SaaSPlanModel.code == plan.code)
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        if record:
            record.name = plan.name
            record.description = plan.description
            record.monthly_price_cents = plan.monthly_price_cents
            record.annual_price_cents = plan.annual_price_cents
            record.currency = plan.currency
            record.included_monthly_minutes = plan.included_monthly_minutes
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
                monthly_price_cents=plan.monthly_price_cents,
                annual_price_cents=plan.annual_price_cents,
                currency=plan.currency,
                included_monthly_minutes=plan.included_monthly_minutes,
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
        return {"message": f"Successfully configured plan {plan.code}"}
