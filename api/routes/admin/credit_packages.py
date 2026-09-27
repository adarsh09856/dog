import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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
    price_cents: int
    currency: str = "INR"
    is_active: bool = True
    sort_order: int = 0


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
                currency=r.currency,
                is_active=r.is_active,
                sort_order=r.sort_order,
            )
            for r in records
        ]


@router.post("", response_model=Dict[str, Any])
async def create_credit_package(pkg: CreditPackageItem, _user=Depends(get_superuser)):
    """Create or update a top-up credit package."""
    async with kodewaves_db_client.get_session() as session:
        if pkg.id:
            stmt = select(CreditPackageModel).where(CreditPackageModel.id == uuid.UUID(pkg.id))
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if not record:
                raise HTTPException(status_code=404, detail="Credit package not found")
            record.name = pkg.name
            record.minutes = pkg.minutes
            record.bonus_minutes = pkg.bonus_minutes
            record.price_cents = pkg.price_cents
            record.currency = pkg.currency
            record.is_active = pkg.is_active
            record.sort_order = pkg.sort_order
        else:
            record = CreditPackageModel(
                name=pkg.name,
                minutes=pkg.minutes,
                bonus_minutes=pkg.bonus_minutes,
                price_cents=pkg.price_cents,
                currency=pkg.currency,
                is_active=pkg.is_active,
                sort_order=pkg.sort_order,
            )
            session.add(record)

        await session.commit()
        return {"message": f"Successfully configured credit package {pkg.name}"}


@router.delete("/{package_id}", response_model=Dict[str, Any])
async def delete_credit_package(package_id: str, _user=Depends(get_superuser)):
    """Deactivate or remove a credit package."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(CreditPackageModel).where(CreditPackageModel.id == uuid.UUID(package_id))
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="Credit package not found")
        record.is_active = False
        await session.commit()
        return {"message": "Credit package deactivated"}
