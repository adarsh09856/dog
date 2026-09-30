from datetime import datetime, UTC
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import CreditPackageModel, OrganizationWalletModel, WalletLedgerModel
from api.db.models import UserModel
from api.services.auth.depends import get_user

router = APIRouter(prefix="/billing-sovereign", tags=["billing-sovereign"])


class WalletResponse(BaseModel):
    organization_id: int
    credit_balance_minutes: int
    bonus_minutes: int
    total_available_minutes: int
    is_frozen: bool


class LedgerItem(BaseModel):
    id: str
    amount_minutes: int
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
    return WalletResponse(
        organization_id=org_id,
        credit_balance_minutes=wallet.credit_balance_minutes,
        bonus_minutes=wallet.bonus_minutes,
        total_available_minutes=wallet.credit_balance_minutes + wallet.bonus_minutes,
        is_frozen=wallet.is_frozen,
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
    """List purchasable minute top-up bundles."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(CreditPackageModel).where(CreditPackageModel.is_active == True).order_by(CreditPackageModel.sort_order)
        result = await session.execute(stmt)
        records = result.scalars().all()

        # Seed default packages if empty
        if not records:
            defaults = [
                CreditPackageModel(name="Starter 100 Minutes", minutes=100, bonus_minutes=0, price_cents=499, currency="INR", sort_order=1),
                CreditPackageModel(name="Growth 500 Minutes", minutes=500, bonus_minutes=50, price_cents=1999, currency="INR", sort_order=2),
                CreditPackageModel(name="Scale 2,000 Minutes", minutes=2000, bonus_minutes=300, price_cents=6999, currency="INR", sort_order=3),
            ]
            for p in defaults:
                session.add(p)
            await session.commit()

            stmt = select(CreditPackageModel).where(CreditPackageModel.is_active == True).order_by(CreditPackageModel.sort_order)
            result = await session.execute(stmt)
            records = result.scalars().all()

        return [
            CreditPackagePublicItem(
                id=str(r.id),
                name=r.name,
                minutes=r.minutes,
                bonus_minutes=r.bonus_minutes,
                price_cents=r.price_cents,
                currency=r.currency,
            )
            for r in records
        ]


class SaaSPlanPublicItem(BaseModel):
    id: str
    name: str
    code: str
    description: Optional[str] = None
    monthly_price_inr: int
    monthly_price_usd: int
    included_minutes: int
    overage_rate_per_minute: float
    max_concurrent_calls: int
    allow_user_byok: bool
    features: List[str] = []
    is_active: bool


@router.get("/public/plans", response_model=List[SaaSPlanPublicItem])
async def list_public_plans():
    """Retrieve public SaaS plans without authentication."""
    async with kodewaves_db_client.get_session() as session:
        from api.db.kodewaves_models import SaaSPlanModel
        stmt = select(SaaSPlanModel).where(SaaSPlanModel.is_active == True)
        result = await session.execute(stmt)
        records = result.scalars().all()

        if not records:
            defaults = [
                SaaSPlanModel(
                    name="Starter", code="starter", description="Ideal for testing voice workflows and prototypes.",
                    monthly_price_cents=1499, included_monthly_minutes=100, max_concurrent_calls=2, allow_user_byok=True
                ),
                SaaSPlanModel(
                    name="Professional", code="pro", description="For growing teams running outbound campaigns and customer service.",
                    monthly_price_cents=4999, included_monthly_minutes=500, max_concurrent_calls=8, allow_user_byok=True
                ),
                SaaSPlanModel(
                    name="Scale / Business", code="scale", description="High concurrency voice agents with dedicated infrastructure.",
                    monthly_price_cents=14999, included_monthly_minutes=2000, max_concurrent_calls=25, allow_user_byok=True
                ),
                SaaSPlanModel(
                    name="Sovereign Enterprise", code="enterprise", description="Zero third-party cloud bills. 100% On-Premise / Private VPS.",
                    monthly_price_cents=34999, included_monthly_minutes=10000, max_concurrent_calls=100, allow_user_byok=True
                ),
            ]
            for p in defaults:
                session.add(p)
            await session.commit()
            result = await session.execute(stmt)
            records = result.scalars().all()

        feature_map = {
            "starter": ["100 Included Voice Minutes", "2 Concurrent Channels", "All 20+ Model Providers", "WebRTC Web Widget", "Visual Node Workflow Builder"],
            "pro": ["500 Included Voice Minutes", "8 Concurrent Channels", "Navana Bodhi 10 Indic Languages", "Twilio & Exotel Native SIP", "System 1 Jev Guardrail", "Priority Support"],
            "scale": ["2,000 Included Voice Minutes", "25 Concurrent Channels", "Lowest ₹0.55/min Internal Route", "Custom Voice Cloning Support", "Direct CRM & Webhook Sync", "Dedicated Account Engineer"],
            "enterprise": ["10,000 Included Voice Minutes", "100+ Concurrent Channels", "Local CPU AI Engine (Ollama + Whisper)", "Zero External Data Transmission", "Full White-Label Branding", "24/7 Phone Support"],
        }

        overage_map = {"starter": 1.20, "pro": 0.95, "scale": 0.75, "enterprise": 0.55}

        return [
            SaaSPlanPublicItem(
                id=str(r.id),
                name=r.name,
                code=r.code,
                description=r.description,
                monthly_price_inr=r.monthly_price_cents,
                monthly_price_usd=max(19, int(r.monthly_price_cents / 83)),
                included_minutes=r.included_monthly_minutes,
                overage_rate_per_minute=overage_map.get(r.code, 1.0),
                max_concurrent_calls=r.max_concurrent_calls,
                allow_user_byok=r.allow_user_byok,
                features=feature_map.get(r.code, ["All Standard Voice Features"]),
                is_active=r.is_active,
            )
            for r in records
        ]


@router.get("/public/packages", response_model=List[CreditPackagePublicItem])
async def list_public_packages():
    """Retrieve public credit top-up bundles without authentication."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(CreditPackageModel).where(CreditPackageModel.is_active == True).order_by(CreditPackageModel.sort_order)
        result = await session.execute(stmt)
        records = result.scalars().all()

        if not records:
            defaults = [
                CreditPackageModel(name="Starter 100 Minutes", minutes=100, bonus_minutes=0, price_cents=499, currency="INR", sort_order=1),
                CreditPackageModel(name="Growth 500 Minutes", minutes=500, bonus_minutes=50, price_cents=1999, currency="INR", sort_order=2),
                CreditPackageModel(name="Scale 2,000 Minutes", minutes=2000, bonus_minutes=300, price_cents=6999, currency="INR", sort_order=3),
            ]
            for p in defaults:
                session.add(p)
            await session.commit()
            result = await session.execute(stmt)
            records = result.scalars().all()

        return [
            CreditPackagePublicItem(
                id=str(r.id),
                name=r.name,
                minutes=r.minutes,
                bonus_minutes=r.bonus_minutes,
                price_cents=r.price_cents,
                currency=r.currency,
            )
            for r in records
        ]


@router.get("/plans", response_model=List[SaaSPlanPublicItem])
async def list_authenticated_plans():
    """Alias for list_public_plans to support frontend billing client."""
    return await list_public_plans()


class SubscribePlanRequest(BaseModel):
    plan_id: Optional[Any] = None
    plan_code: Optional[str] = None


@router.post("/subscribe")
async def subscribe_to_plan(req: SubscribePlanRequest, user: UserModel = Depends(get_user)):
    """Subscribe user's organization to a SaaS plan and grant initial plan minutes."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    from api.db.kodewaves_models import SaaSPlanModel
    import uuid

    target_code = req.plan_code
    async with kodewaves_db_client.get_session() as session:
        query = select(SaaSPlanModel)
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
        if not plan:
            # Fallback to starter plan
            plan_res = await session.execute(select(SaaSPlanModel).where(SaaSPlanModel.code == "starter"))
            plan = plan_res.scalar_one_or_none()

        plan_code = plan.code if plan else "starter"
        minutes = plan.included_monthly_minutes if plan else 100

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

        # Grant monthly plan minutes
        wallet = await kodewaves_db_client.add_minutes(
            organization_id=org_id,
            minutes=minutes,
            reason="plan_subscription",
            reference_id=str(plan.id) if plan else "sub_starter",
            notes=f"Subscribed to {plan.name if plan else 'Starter'} Plan",
        )

        return {
            "message": f"Successfully subscribed to {plan.name if plan else 'Starter'} plan",
            "plan_code": plan_code,
            "wallet_balance_minutes": wallet.credit_balance_minutes,
        }

