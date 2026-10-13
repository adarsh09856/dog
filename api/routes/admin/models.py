from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.db.kodewaves_client import kodewaves_db_client
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


from api.services.catalog.catalog_service import catalog_service

@router.get("", response_model=List[ModelCatalogItem])
async def list_models(category: Optional[str] = None, _user=Depends(get_superuser)):
    records = await kodewaves_db_client.list_models(layer=category, enabled_only=False)
    output = []
    for record in records:
        cost = float(record.base_cost_cents_per_unit)
        rate = float(record.retail_price_cents_per_unit)
        margin = round(((rate - cost) / max(0.001, rate)) * 100, 1) if rate > cost else 0.0
        output.append(ModelCatalogItem(
            id=str(record.id), model_identifier=record.model_identifier,
            model_id=record.model_identifier, display_name=record.display_name,
            provider=record.provider, category=record.category,
            base_cost_cents_per_unit=cost, retail_price_cents_per_unit=rate,
            cost_per_minute=cost, rate_per_minute=rate, markup_margin_percent=margin,
            custom_base_url=record.custom_base_url, allowed_plan_ids=record.allowed_plan_ids or [],
            is_active=record.is_active, sort_order=record.sort_order,
        ))
    return output


def _catalog_values(item: ModelCatalogItem) -> Dict[str, Any]:
    values = item.model_dump()
    values["model_identifier"] = item.model_identifier or item.model_id
    values["provider"] = item.provider.lower().strip()
    values["category"] = item.category.lower().strip()
    if values["category"] not in ("llm", "stt", "tts", "sts", "realtime", "s2s", "embeddings"):
        raise HTTPException(status_code=422, detail="Unsupported model category")
    values["base_cost_cents_per_unit"] = item.cost_per_minute if "cost_per_minute" in item.model_fields_set else item.base_cost_cents_per_unit
    values["retail_price_cents_per_unit"] = item.rate_per_minute if "rate_per_minute" in item.model_fields_set else item.retail_price_cents_per_unit
    return values


@router.post("", response_model=Dict[str, Any])
async def upsert_model(item: ModelCatalogItem, _user=Depends(get_superuser)):
    values = _catalog_values(item)
    if not values["model_identifier"]:
        raise HTTPException(status_code=400, detail="model_identifier or model_id is required")
    record = await kodewaves_db_client.configure_admin_model(values)
    await catalog_service.notify_changed()
    return {"message": f"Successfully configured model {record.model_identifier}", "id": str(record.id)}


@router.put("/{model_id}", response_model=Dict[str, Any])
async def update_model_by_id(model_id: str, item: ModelCatalogItem, _user=Depends(get_superuser)):
    record = await kodewaves_db_client.configure_admin_model(_catalog_values(item), model_id=model_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Model not found")
    await catalog_service.notify_changed()
    return {"message": f"Successfully updated model {record.model_identifier}", "id": str(record.id)}


@router.delete("/{model_id}", response_model=Dict[str, Any])
async def delete_model_by_id(model_id: str, _user=Depends(get_superuser)):
    if not await kodewaves_db_client.delete_admin_model(model_id):
        raise HTTPException(status_code=404, detail="Model not found")
    await catalog_service.notify_changed()
    return {"message": f"Successfully deleted model {model_id}"}


@router.patch("/{model_id}/toggle", response_model=Dict[str, Any])
async def toggle_model(model_id: str, _user=Depends(get_superuser)):
    active = await kodewaves_db_client.toggle_admin_model(model_id)
    if active is None:
        raise HTTPException(status_code=404, detail="Model not found")
    await catalog_service.notify_changed()
    return {"id": model_id, "is_active": active}
