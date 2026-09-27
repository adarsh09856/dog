import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import AIModelCatalogModel
from api.services.auth.depends import get_superuser

router = APIRouter(prefix="/models", tags=["admin-models"])


class ModelCatalogItem(BaseModel):
    id: Optional[str] = None
    model_identifier: str
    display_name: str
    provider: str
    category: str
    base_cost_cents_per_unit: float = 0.0
    retail_price_cents_per_unit: float = 0.0
    custom_base_url: Optional[str] = None
    allowed_plan_ids: List[str] = []
    is_active: bool = True
    sort_order: int = 0


@router.get("", response_model=List[ModelCatalogItem])
async def list_models(category: Optional[str] = None, _user=Depends(get_superuser)):
    """List all AI models with pricing margins and plan assignments."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(AIModelCatalogModel).order_by(AIModelCatalogModel.sort_order)
        if category:
            stmt = stmt.where(AIModelCatalogModel.category == category)
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [
            ModelCatalogItem(
                id=str(r.id),
                model_identifier=r.model_identifier,
                display_name=r.display_name,
                provider=r.provider,
                category=r.category,
                base_cost_cents_per_unit=r.base_cost_cents_per_unit,
                retail_price_cents_per_unit=r.retail_price_cents_per_unit,
                custom_base_url=r.custom_base_url,
                allowed_plan_ids=r.allowed_plan_ids or [],
                is_active=r.is_active,
                sort_order=r.sort_order,
            )
            for r in records
        ]


@router.post("", response_model=Dict[str, Any])
async def upsert_model(item: ModelCatalogItem, _user=Depends(get_superuser)):
    """Add or update a model in the catalog."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.model_identifier == item.model_identifier)
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        if record:
            record.display_name = item.display_name
            record.provider = item.provider
            record.category = item.category
            record.base_cost_cents_per_unit = item.base_cost_cents_per_unit
            record.retail_price_cents_per_unit = item.retail_price_cents_per_unit
            record.custom_base_url = item.custom_base_url
            record.allowed_plan_ids = item.allowed_plan_ids
            record.is_active = item.is_active
            record.sort_order = item.sort_order
        else:
            record = AIModelCatalogModel(
                model_identifier=item.model_identifier,
                display_name=item.display_name,
                provider=item.provider,
                category=item.category,
                base_cost_cents_per_unit=item.base_cost_cents_per_unit,
                retail_price_cents_per_unit=item.retail_price_cents_per_unit,
                custom_base_url=item.custom_base_url,
                allowed_plan_ids=item.allowed_plan_ids,
                is_active=item.is_active,
                sort_order=item.sort_order,
            )
            session.add(record)

        await session.commit()
        return {"message": f"Successfully configured model {item.model_identifier}"}


@router.patch("/{model_id}/toggle", response_model=Dict[str, Any])
async def toggle_model(model_id: str, _user=Depends(get_superuser)):
    """Toggle a model active or inactive globally."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.id == uuid.UUID(model_id))
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="Model not found")

        record.is_active = not record.is_active
        await session.commit()
        return {"id": model_id, "is_active": record.is_active}
