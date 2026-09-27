from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.db.kodewaves_client import kodewaves_db_client
from api.services.auth.depends import get_superuser
from api.services.credentials.master_credential_service import master_credential_service

router = APIRouter(prefix="/master-keys", tags=["admin-master-keys"])


class MasterCredentialRequest(BaseModel):
    provider: str
    category: str
    credentials: Dict[str, Any]
    is_enabled: bool = True


class MasterCredentialResponse(BaseModel):
    provider: str
    category: str
    is_enabled: bool
    health_status: str
    last_tested_at: Optional[str] = None
    has_credentials: bool = True


class TestConnectionResponse(BaseModel):
    success: bool
    message: str


@router.get("", response_model=List[MasterCredentialResponse])
async def list_master_keys(_user=Depends(get_superuser)):
    """List all configured master credentials with masked status."""
    records = await kodewaves_db_client.list_master_credentials()
    return [
        MasterCredentialResponse(
            provider=r.provider,
            category=r.category,
            is_enabled=r.is_enabled,
            health_status=r.health_status,
            last_tested_at=r.last_tested_at.isoformat() if r.last_tested_at else None,
            has_credentials=bool(r.credentials_encrypted),
        )
        for r in records
    ]


@router.post("", response_model=Dict[str, Any])
async def save_master_key(req: MasterCredentialRequest, _user=Depends(get_superuser)):
    """Encrypt and save master credentials for a provider."""
    success = await master_credential_service.save_master_credential(
        provider=req.provider,
        category=req.category,
        credentials_dict=req.credentials,
        is_enabled=req.is_enabled,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to encrypt and store master credentials.")
    return {"message": f"Successfully stored master credentials for {req.provider}"}


@router.post("/{provider}/test", response_model=TestConnectionResponse)
async def test_master_key_connection(provider: str, _user=Depends(get_superuser)):
    """Perform live connectivity check to upstream provider."""
    success, message = await master_credential_service.test_connection(provider)
    # Update health status in DB
    status_str = "healthy" if success else "invalid"
    await kodewaves_db_client.upsert_master_credential(
        provider=provider.lower().strip(),
        category="llm",  # Will retain existing category in update
        credentials_encrypted="",  # Will retain existing in update
        is_enabled=True,
        health_status=status_str,
    )
    return TestConnectionResponse(success=success, message=message)
