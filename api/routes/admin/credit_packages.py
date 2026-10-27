from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.db import credit_package_catalog
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


def _package_values(pkg: CreditPackageItem) -> dict:
    return {
        "name": pkg.name, "minutes": pkg.minutes, "bonus_minutes": pkg.bonus_minutes,
        "price_cents": _configured_package_price_cents(pkg), "currency": pkg.currency,
        "is_popular": pkg.is_popular, "is_active": pkg.is_active, "sort_order": pkg.sort_order,
    }


@router.get("", response_model=List[CreditPackageItem])
async def list_credit_packages(_user=Depends(get_superuser)):
    """List all top-up credit packages."""
    records = await credit_package_catalog.list_packages()
    return [CreditPackageItem(
        id=str(r.id), name=r.name, minutes=r.minutes, bonus_minutes=r.bonus_minutes,
        price_cents=r.price_cents,
        price_inr=r.price_cents / 100 if r.currency == "INR" else None,
        price_usd=r.price_cents / 100 if r.currency == "USD" else None,
        currency=r.currency, is_popular=r.is_popular, is_active=r.is_active,
        sort_order=r.sort_order,
    ) for r in records]


@router.post("", response_model=Dict[str, Any])
async def create_credit_package(pkg: CreditPackageItem, _user=Depends(get_superuser)):
    """Create or upsert a top-up credit package."""
    record = await credit_package_catalog.create_package(_package_values(pkg))
    return {"message": f"Successfully created package {pkg.name}", "id": str(record.id)}


@router.put("/{package_id}", response_model=Dict[str, Any])
async def update_credit_package(package_id: str, pkg: CreditPackageItem, _user=Depends(get_superuser)):
    """Update an existing credit package by ID."""
    record = await credit_package_catalog.update_package(package_id, _package_values(pkg))
    if record is None:
        raise HTTPException(status_code=404, detail="Credit package not found")
    return {"message": f"Successfully updated package {record.name}", "id": str(record.id)}


@router.delete("/{package_id}", response_model=Dict[str, Any])
async def delete_credit_package(package_id: str, _user=Depends(get_superuser)):
    """Remove a credit package by ID."""
    if not await credit_package_catalog.delete_package(package_id):
        raise HTTPException(status_code=404, detail="Credit package not found")
    return {"message": "Credit package deleted successfully"}
