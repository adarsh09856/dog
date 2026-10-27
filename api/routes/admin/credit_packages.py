import uuid
from typing import Any, Dict, List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import CreditPackageModel
from api.services.auth.depends import get_superuser

router = APIRouter(prefix="/credit-packages", tags=["admin-credit-packages"])


class CreditPackageItem(BaseModel):
    id: Optional[str] = None
    name: str
    minutes: int
    bonus_minutes: int = 0
    price_cents: int = Field(default=0, ge=0)
    price_inr: Optional[float] = Field(default=None, ge=0)
    price_usd: Optional[float] = Field(default=None, ge=0)
    currency: Literal["INR", "USD"] = "INR"
    is_popular: bool = False
    is_active: bool = True
    sort_order: int = 0


def _configured_package_price_cents(package: CreditPackageItem) -> int:
    """Use exact minor units; accept legacy same-currency major units only when omitted."""
    if "price_cents" in package.model_fields_set:
        return package.price_cents
    legacy_amount = package.price_inr if package.currency == "INR" else package.price_usd
    return round(legacy_amount * 100) if legacy_amount is not None else 0


@router.get("", response_model=List[CreditPackageItem])
async def list_credit_packages(_user=Depends(get_superuser)):
    """List all top-up credit packages."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(CreditPackageModel).order_by(CreditPackageModel.sort_order)
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [
            CreditPackageItem(
                id=str(r.id),
                name=r.name,
                minutes=r.minutes,
                bonus_minutes=r.bonus_minutes,
                price_cents=r.price_cents,
                price_inr=float(r.price_cents / 100.0) if r.currency == "INR" else None,
                price_usd=float(r.price_cents / 100.0) if r.currency == "USD" else None,
                currency=r.currency,
                is_popular=bool(r.bonus_minutes > 0),
                is_active=r.is_active,
                sort_order=r.sort_order,
            )
            for r in records
        ]


@router.post("", response_model=Dict[str, Any])
async def create_credit_package(pkg: CreditPackageItem, _user=Depends(get_superuser)):
    """Create or upsert a top-up credit package."""
    cents = _configured_package_price_cents(pkg)

    async with kodewaves_db_client.get_session() as session:
        record = CreditPackageModel(
            name=pkg.name,
            minutes=pkg.minutes,
            bonus_minutes=pkg.bonus_minutes,
            price_cents=cents,
            currency=pkg.currency,
            is_active=pkg.is_active,
            sort_order=pkg.sort_order,
        )
        session.add(record)
        await session.commit()
        return {"message": f"Successfully created package {pkg.name}", "id": str(record.id)}


@router.put("/{package_id}", response_model=Dict[str, Any])
async def update_credit_package(package_id: str, pkg: CreditPackageItem, _user=Depends(get_superuser)):
    """Update an existing credit package by ID."""
    cents = _configured_package_price_cents(pkg)

    async with kodewaves_db_client.get_session() as session:
        try:
            pkg_uuid = uuid.UUID(package_id)
            stmt = select(CreditPackageModel).where(CreditPackageModel.id == pkg_uuid)
        except ValueError:
            stmt = select(CreditPackageModel).where(CreditPackageModel.name == package_id)

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="Credit package not found")

        record.name = pkg.name
        record.minutes = pkg.minutes
        record.bonus_minutes = pkg.bonus_minutes
        record.price_cents = cents
        record.currency = pkg.currency
        record.is_active = pkg.is_active
        record.sort_order = pkg.sort_order

        await session.commit()
        return {"message": f"Successfully updated package {record.name}", "id": str(record.id)}


@router.delete("/{package_id}", response_model=Dict[str, Any])
async def delete_credit_package(package_id: str, _user=Depends(get_superuser)):
    """Remove a credit package by ID."""
    async with kodewaves_db_client.get_session() as session:
        try:
            pkg_uuid = uuid.UUID(package_id)
            stmt = select(CreditPackageModel).where(CreditPackageModel.id == pkg_uuid)
        except ValueError:
            stmt = select(CreditPackageModel).where(CreditPackageModel.name == package_id)

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="Credit package not found")

        await session.delete(record)
        await session.commit()
        return {"message": "Credit package deleted successfully"}
