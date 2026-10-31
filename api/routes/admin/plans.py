from typing import Any, Dict, List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.db import saas_plan_catalog
from api.services.auth.depends import get_superuser

router = APIRouter(prefix="/plans", tags=["admin-plans"])


class PlanItem(BaseModel):
    id: Optional[str] = None
    name: str
    code: str
    description: Optional[str] = None
    monthly_price_cents: int = Field(default=0, ge=0)
    monthly_price_inr: Optional[float] = Field(default=None, ge=0)
    monthly_price_usd: Optional[float] = Field(default=None, ge=0)
    annual_price_cents: int = Field(default=0, ge=0)
    currency: Literal["INR", "USD"] = "INR"
    included_monthly_minutes: int = Field(default=60, ge=0)
    included_minutes: int = Field(default=60, ge=0)
    max_agents: int = Field(default=3, ge=0)
    max_concurrent_calls: int = Field(default=2, ge=0)
    has_crm_access: bool = True
    has_appointments_access: bool = True
    has_forms_access: bool = True
    has_widget_access: bool = True
    has_campaigns_access: bool = True
    allow_user_byok: bool = False
    is_default: bool = False
    is_active: bool = True
    is_public: bool = True


def _configured_monthly_price_cents(plan: PlanItem) -> int:
    """Use exact minor units; accept legacy same-currency major units only when omitted."""
    if "monthly_price_cents" in plan.model_fields_set:
        return plan.monthly_price_cents
    legacy_amount = plan.monthly_price_inr if plan.currency == "INR" else plan.monthly_price_usd
    return round(legacy_amount * 100) if legacy_amount is not None else 0


def _configured_included_minutes(plan: PlanItem) -> int:
    """Preserve an explicit zero; only fall back for legacy field-only callers."""
    return plan.included_minutes if "included_minutes" in plan.model_fields_set else plan.included_monthly_minutes


def _plan_values(plan: PlanItem) -> dict:
    return {
        "name": plan.name, "code": plan.code, "description": plan.description,
        "monthly_price_cents": _configured_monthly_price_cents(plan),
        "annual_price_cents": plan.annual_price_cents, "currency": plan.currency,
        "included_monthly_minutes": _configured_included_minutes(plan),
        "max_agents": plan.max_agents, "max_concurrent_calls": plan.max_concurrent_calls,
        "has_crm_access": plan.has_crm_access,
        "has_appointments_access": plan.has_appointments_access,
        "has_forms_access": plan.has_forms_access, "has_widget_access": plan.has_widget_access,
        "has_campaigns_access": plan.has_campaigns_access,
        "allow_user_byok": plan.allow_user_byok,
        "is_default": plan.is_default, "is_active": plan.is_active,
        "is_public": plan.is_public,
    }


def _validate_new_plan_price(plan: PlanItem) -> None:
    """Require an explicit pricing decision before activating or publishing."""
    explicit_price_fields = {"monthly_price_cents", "annual_price_cents"}
    if plan.currency == "INR":
        explicit_price_fields.add("monthly_price_inr")
    else:
        explicit_price_fields.add("monthly_price_usd")
    if (plan.is_active or plan.is_public) and not plan.model_fields_set.intersection(explicit_price_fields):
        raise HTTPException(
            status_code=422,
            detail="Set a monthly or annual price, including zero for an intentional free plan, before activating or publishing a plan",
        )


@router.get("", response_model=List[PlanItem])
async def list_plans(_user=Depends(get_superuser)):
    records = await saas_plan_catalog.list_plans()
    return [
        PlanItem(
            id=str(r.id), name=r.name, code=r.code, description=r.description,
            monthly_price_cents=r.monthly_price_cents,
            monthly_price_inr=r.monthly_price_cents / 100 if r.currency == "INR" else None,
            monthly_price_usd=r.monthly_price_cents / 100 if r.currency == "USD" else None,
            annual_price_cents=r.annual_price_cents, currency=r.currency,
            included_monthly_minutes=r.included_monthly_minutes,
            included_minutes=r.included_monthly_minutes, max_agents=r.max_agents,
            max_concurrent_calls=r.max_concurrent_calls,
            has_crm_access=r.has_crm_access, has_appointments_access=r.has_appointments_access,
            has_forms_access=r.has_forms_access, has_widget_access=r.has_widget_access,
            has_campaigns_access=r.has_campaigns_access,
            allow_user_byok=r.allow_user_byok, is_default=r.is_default,
            is_active=r.is_active, is_public=r.is_public,
        ) for r in records
    ]


@router.post("", response_model=Dict[str, Any])
async def upsert_plan(plan: PlanItem, _user=Depends(get_superuser)):
    _validate_new_plan_price(plan)
    try:
        record = await saas_plan_catalog.save_plan(_plan_values(plan))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"message": f"Successfully configured plan '{record.name}'", "id": str(record.id)}


@router.put("/{plan_id}", response_model=Dict[str, Any])
async def update_plan(plan_id: str, plan: PlanItem, _user=Depends(get_superuser)):
    try:
        record = await saas_plan_catalog.save_plan(_plan_values(plan), identifier=plan_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if record is None:
        raise HTTPException(status_code=404, detail="SaaS Plan not found")
    return {"message": f"Successfully updated plan '{record.name}'", "id": str(record.id)}


@router.delete("/{plan_id}", response_model=Dict[str, Any])
async def delete_plan(plan_id: str, _user=Depends(get_superuser)):
    name = await saas_plan_catalog.delete_plan(plan_id)
    if name is None:
        raise HTTPException(status_code=404, detail="SaaS Plan not found")
    return {"message": f"Successfully deleted plan '{name}'"}
