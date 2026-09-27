from typing import Any, Dict
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.db.kodewaves_client import kodewaves_db_client
from api.services.auth.depends import get_superuser

router = APIRouter(prefix="/settings", tags=["admin-settings"])


class SettingsUpdateRequest(BaseModel):
    category: str
    key: str
    value: Dict[str, Any]


@router.get("/{key}")
async def get_admin_setting(key: str, _user=Depends(get_superuser)):
    """Retrieve platform configuration by key."""
    val = await kodewaves_db_client.get_setting(key)
    return {"key": key, "value": val or {}}


@router.post("")
async def update_admin_setting(req: SettingsUpdateRequest, _user=Depends(get_superuser)):
    """Save or update platform configuration."""
    setting = await kodewaves_db_client.set_setting(
        key=req.key,
        value=req.value,
        category=req.category,
    )
    return {"message": f"Successfully updated {req.key}", "setting": setting.value}
