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
    model_identifier: Optional[str] = None
    model_id: Optional[str] = None
    display_name: str
    provider: str
    category: str
    base_cost_cents_per_unit: float = 0.0
    retail_price_cents_per_unit: float = 0.0
    cost_per_minute: float = 0.0
    rate_per_minute: float = 0.0
    markup_margin_percent: float = 0.0
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

        output = []
        for r in records:
            cost = float(r.base_cost_cents_per_unit)
            rate = float(r.retail_price_cents_per_unit)
            margin = round(((rate - cost) / max(0.001, rate)) * 100, 1) if rate > cost else 0.0

            output.append(
                ModelCatalogItem(
                    id=str(r.id),
                    model_identifier=r.model_identifier,
                    model_id=r.model_identifier,
                    display_name=r.display_name,
                    provider=r.provider,
                    category=r.category,
                    base_cost_cents_per_unit=cost,
                    retail_price_cents_per_unit=rate,
                    cost_per_minute=cost,
                    rate_per_minute=rate,
                    markup_margin_percent=margin,
                    custom_base_url=r.custom_base_url,
                    allowed_plan_ids=r.allowed_plan_ids or [],
                    is_active=r.is_active,
                    sort_order=r.sort_order,
                )
            )

        return output


@router.post("", response_model=Dict[str, Any])
async def upsert_model(item: ModelCatalogItem, _user=Depends(get_superuser)):
    """Add or update a model in the catalog."""
    ident = item.model_identifier or item.model_id
    if not ident:
        raise HTTPException(status_code=400, detail="model_identifier or model_id is required")

    cost = item.cost_per_minute if item.cost_per_minute > 0 else item.base_cost_cents_per_unit
    rate = item.rate_per_minute if item.rate_per_minute > 0 else item.retail_price_cents_per_unit

    async with kodewaves_db_client.get_session() as session:
        stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.model_identifier == ident)
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        if record:
            record.display_name = item.display_name
            record.provider = item.provider
            record.category = item.category
            record.base_cost_cents_per_unit = cost
            record.retail_price_cents_per_unit = rate
            record.custom_base_url = item.custom_base_url
            record.allowed_plan_ids = item.allowed_plan_ids
            record.is_active = item.is_active
            record.sort_order = item.sort_order
        else:
            record = AIModelCatalogModel(
                model_identifier=ident,
                display_name=item.display_name,
                provider=item.provider,
                category=item.category,
                base_cost_cents_per_unit=cost,
                retail_price_cents_per_unit=rate,
                custom_base_url=item.custom_base_url,
                allowed_plan_ids=item.allowed_plan_ids,
                is_active=item.is_active,
                sort_order=item.sort_order,
            )
            session.add(record)

        await session.commit()
        return {"message": f"Successfully configured model {ident}", "id": str(record.id)}


@router.put("/{model_id}", response_model=Dict[str, Any])
async def update_model_by_id(model_id: str, item: ModelCatalogItem, _user=Depends(get_superuser)):
    """Update a model's properties and margins by ID."""
    cost = item.cost_per_minute if item.cost_per_minute > 0 else item.base_cost_cents_per_unit
    rate = item.rate_per_minute if item.rate_per_minute > 0 else item.retail_price_cents_per_unit

    async with kodewaves_db_client.get_session() as session:
        try:
            m_uuid = uuid.UUID(model_id)
            stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.id == m_uuid)
        except ValueError:
            stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.model_identifier == model_id)

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="Model not found")

        record.display_name = item.display_name
        record.provider = item.provider
        record.category = item.category
        record.base_cost_cents_per_unit = cost
        record.retail_price_cents_per_unit = rate
        record.custom_base_url = item.custom_base_url
        record.allowed_plan_ids = item.allowed_plan_ids
        record.is_active = item.is_active
        record.sort_order = item.sort_order

        await session.commit()
        return {"message": f"Successfully updated model {record.model_identifier}", "id": str(record.id)}


@router.delete("/{model_id}", response_model=Dict[str, Any])
async def delete_model_by_id(model_id: str, _user=Depends(get_superuser)):
    """Delete a model from the catalog."""
    async with kodewaves_db_client.get_session() as session:
        try:
            m_uuid = uuid.UUID(model_id)
            stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.id == m_uuid)
        except ValueError:
            stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.model_identifier == model_id)

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="Model not found")

        await session.delete(record)
        await session.commit()
        return {"message": f"Successfully deleted model {model_id}"}


@router.patch("/{model_id}/toggle", response_model=Dict[str, Any])
async def toggle_model(model_id: str, _user=Depends(get_superuser)):
    """Toggle a model active or inactive globally."""
    async with kodewaves_db_client.get_session() as session:
        try:
            m_uuid = uuid.UUID(model_id)
            stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.id == m_uuid)
        except ValueError:
            stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.model_identifier == model_id)

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="Model not found")

        record.is_active = not record.is_active
        await session.commit()
        return {"id": model_id, "is_active": record.is_active}
