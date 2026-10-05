"""
Catalog Routes — Dynamic Provider, Model & Voice capability manifests for Studio & Organization settings.
Powered purely by the Database Truth Layer (ai_model_catalog & voice_catalog).
No hardcoded models or voices.
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends

from api.db.models import UserModel
from api.services.auth.depends import get_user
from api.services.catalog.catalog_service import catalog_service

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/available")
async def get_available_catalog(
    user: UserModel = Depends(get_user),
) -> Dict[str, Any]:
    """
    Returns dynamic list of models and engines actually available to this organization:
    1. Returns cloud models backed by verified active master keys or authorized BYOK.
    2. Returns local LLM/STT/TTS models if and only if local AI is enabled and accessible.
    3. Respects organization AI policy.
    """
    org_id = getattr(user, "organization_id", 0) or 0
    has_local = getattr(user, "has_local_ai_access", True)
    if has_local is None:
        has_local = True

    return await catalog_service.get_available_catalog(
        organization_id=org_id,
        user_has_local_ai=bool(has_local),
    )
