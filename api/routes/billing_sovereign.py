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
