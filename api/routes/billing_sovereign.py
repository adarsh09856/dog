from datetime import datetime, UTC
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.public_pricing import list_active_plans, list_active_credit_packages
from api.db.kodewaves_models import (
    CreditPackageModel,
    OrganizationWalletModel,
    SaaSPlanModel,
    WalletLedgerModel,
)
from api.db.models import UserModel
from api.services.auth.depends import get_user
from api.services.saas_entitlements import active_plan_code, get_org_saas_plan

router = APIRouter(prefix="/billing-sovereign", tags=["billing-sovereign"])


class WalletResponse(BaseModel):
    organization_id: int
    credit_balance_minutes: int
    bonus_minutes: int
    total_available_minutes: int
    is_frozen: bool
    plan_code: Optional[str] = None
    plan_name: Optional[str] = None
    included_minutes: Optional[int] = None
    plan_expires_at: Optional[str] = None


class LedgerItem(BaseModel):
    id: str
    amount_minutes: int
    delta_minutes: int = 0
    balance_after: int
    reason: str
    reference_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: str


class CreditPackagePublicItem(BaseModel):
    id: str
    name: str
    minutes: int
    bonus_minutes: int
    price_cents: int
    currency: str


@router.get("/wallet", response_model=WalletResponse)
async def get_wallet(user: UserModel = Depends(get_user)):
    """Retrieve organization minute balance."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    wallet = await kodewaves_db_client.get_or_create_wallet(org_id)
    assigned_plan = await kodewaves_db_client.get_setting(f"org_plan_{org_id}") or {}
    assigned_code = active_plan_code(assigned_plan)
    active_plan = await get_org_saas_plan(org_id)
    plan_code = active_plan.code if active_plan else None
    plan_name = active_plan.name if active_plan else None
    included_minutes = active_plan.included_monthly_minutes if active_plan else None
    plan_expires_at = (
        assigned_plan.get("expires_at")
        if assigned_code and active_plan and assigned_code == active_plan.code
        else None
    )
    return WalletResponse(
        organization_id=org_id,
        credit_balance_minutes=wallet.credit_balance_minutes,
        bonus_minutes=wallet.bonus_minutes,
        total_available_minutes=wallet.credit_balance_minutes + wallet.bonus_minutes,
        is_frozen=wallet.is_frozen,
        plan_code=plan_code,
        plan_name=plan_name,
        included_minutes=included_minutes,
        plan_expires_at=plan_expires_at,
    )


@router.get("/ledger", response_model=List[LedgerItem])
async def get_ledger(limit: int = 50, user: UserModel = Depends(get_user)):
    """Retrieve organization credit transaction history."""
    org_id = user.selected_organization_id
    if not org_id:
        return []

    async with kodewaves_db_client.get_session() as session:
        stmt = (
            select(WalletLedgerModel)
            .where(WalletLedgerModel.organization_id == org_id)
            .order_by(desc(WalletLedgerModel.created_at))
            .limit(limit)
        )
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [
            LedgerItem(
                id=str(r.id),
                amount_minutes=r.amount_minutes,
                delta_minutes=r.amount_minutes,
                balance_after=r.balance_after,
                reason=r.reason,
                reference_id=r.reference_id,
                notes=r.notes,
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in records
        ]


@router.get("/packages", response_model=List[CreditPackagePublicItem])
async def list_available_packages(_user=Depends(get_user)):
    """List configured credit bundles without inventing offers on a read."""
    records = await list_active_credit_packages()
    return [CreditPackagePublicItem(
        id=str(r.id), name=r.name, minutes=r.minutes,
        bonus_minutes=r.bonus_minutes, price_cents=r.price_cents, currency=r.currency,
    ) for r in records]


class SaaSPlanPublicItem(BaseModel):
    id: str
    name: str
    code: str
    description: Optional[str] = None
    monthly_price_inr: Optional[float] = None
    monthly_price_usd: Optional[float] = None
    included_minutes: int
    overage_rate_per_minute: Optional[float] = None
    monthly_price_cents: int = 0
    annual_price_cents: int = 0
    currency: str = "INR"
    max_concurrent_calls: int
    allow_user_byok: bool
    features: List[str] = []
    is_active: bool


def _legacy_plan_prices(price_cents: int, currency: str) -> tuple[float | None, float | None]:
    """Expose the stored amount only in its configured currency; never estimate FX."""
    amount = max(0, int(price_cents or 0))
    normalized_currency = str(currency or "").upper()
    if normalized_currency == "INR":
        return amount / 100, None
    if normalized_currency == "USD":
        return None, amount / 100
    return None, None


def _requires_paid_checkout(plan_code: str, plan: SaaSPlanModel | None) -> bool:
    return bool(
        plan
        and (plan.monthly_price_cents > 0 or plan.annual_price_cents > 0)
    )


@router.get("/public/plans", response_model=List[SaaSPlanPublicItem])
async def list_public_plans():
    """Return configured active plans and exact stored prices; never seed on read."""
    records = await list_active_plans()
    return [
        SaaSPlanPublicItem(
            id=str(r.id), name=r.name, code=r.code, description=r.description,
            monthly_price_inr=_legacy_plan_prices(r.monthly_price_cents, r.currency)[0],
            monthly_price_usd=_legacy_plan_prices(r.monthly_price_cents, r.currency)[1],
            monthly_price_cents=r.monthly_price_cents,
            annual_price_cents=r.annual_price_cents,
            currency=r.currency,
            included_minutes=r.included_monthly_minutes,
            max_concurrent_calls=r.max_concurrent_calls,
            allow_user_byok=r.allow_user_byok,
            features=[label for enabled, label in (
                (r.has_crm_access, "CRM access"),
                (r.has_appointments_access, "Appointment tools"),
                (r.has_forms_access, "Forms"),
                (r.has_widget_access, "Web widgets"),
                (r.allow_user_byok, "Bring your own provider keys"),
            ) if enabled],
            is_active=r.is_active,
        ) for r in records
    ]


@router.get("/public/packages", response_model=List[CreditPackagePublicItem])
async def list_public_packages():
    """Return configured active credit bundles without creating sample offers."""
    records = await list_active_credit_packages()
    return [CreditPackagePublicItem(
        id=str(r.id), name=r.name, minutes=r.minutes,
        bonus_minutes=r.bonus_minutes, price_cents=r.price_cents, currency=r.currency,
    ) for r in records]


@router.get("/plans", response_model=List[SaaSPlanPublicItem])
async def list_authenticated_plans(_user: UserModel = Depends(get_user)):
    """Authenticated endpoint for SaaS plans with current user session."""
    return await list_public_plans()


class SubscribePlanRequest(BaseModel):
    plan_id: Optional[Any] = None
    plan_code: Optional[str] = None


@router.post("/subscribe")
async def subscribe_to_plan(req: SubscribePlanRequest, user: UserModel = Depends(get_user)):
    """Subscribe user's organization to a SaaS plan. Paid plans require checkout verification."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    from api.db.kodewaves_models import SaaSPlanModel
    import uuid

    target_code = req.plan_code
    if not req.plan_id and not target_code:
        raise HTTPException(status_code=422, detail="Plan ID or code is required")
    async with kodewaves_db_client.get_session() as session:
        query = select(SaaSPlanModel).where(SaaSPlanModel.is_public.is_(True))
        if req.plan_id:
            try:
                p_uuid = uuid.UUID(str(req.plan_id))
                query = query.where(SaaSPlanModel.id == p_uuid)
            except (ValueError, TypeError):
                query = query.where(
                    (SaaSPlanModel.code == str(req.plan_id)) | (SaaSPlanModel.name == str(req.plan_id))
                )
        elif target_code:
            query = query.where(SaaSPlanModel.code == target_code)

        result = await session.execute(query)
        plan = result.scalar_one_or_none()
        if not plan or not plan.is_active or not plan.is_public:
            raise HTTPException(status_code=404, detail="Active plan not found")

        plan_code = plan.code

        # Security check: Paid tiers require payment checkout
        if _requires_paid_checkout(plan_code, plan):
            raise HTTPException(
                status_code=402,
                detail=f"Plan '{plan.name}' requires payment verification. Please complete subscription checkout via /payments/create-order.",
            )

        existing_plan = await kodewaves_db_client.get_setting(f"org_plan_{org_id}")
        wallet = await kodewaves_db_client.get_or_create_wallet(org_id)

        # Starter tier can only grant trial minutes once per organization
        if existing_plan:
            return {
                "message": f"Organization is already on {existing_plan.get('plan_name', 'Starter')} plan",
                "plan_code": existing_plan.get("plan_code", plan_code),
                "wallet_balance_minutes": wallet.credit_balance_minutes,
            }

        minutes = plan.included_monthly_minutes

        # Save plan assignment in org settings
        await kodewaves_db_client.set_setting(
            f"org_plan_{org_id}",
            {
                "plan_code": plan_code,
                "plan_name": plan.name if plan else "Starter",
                "updated_at": datetime.now(UTC).isoformat(),
            },
            category="plan",
        )

        # Grant initial trial plan minutes
        wallet = await kodewaves_db_client.add_minutes(
            organization_id=org_id,
            minutes=minutes,
            reason="plan_subscription",
            reference_id=str(plan.id) if plan else "sub_starter",
            notes=f"Subscribed to {plan.name if plan else 'Starter'} Plan (Trial Minutes)",
        )

        return {
            "message": f"Successfully subscribed to {plan.name if plan else 'Starter'} plan",
            "plan_code": plan_code,
            "wallet_balance_minutes": wallet.credit_balance_minutes,
        }

