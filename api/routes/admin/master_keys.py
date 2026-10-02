from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import PlatformMasterCredentialModel
from api.services.auth.depends import get_superuser
from api.services.credentials.master_credential_service import master_credential_service

router = APIRouter(prefix="/master-keys", tags=["admin-master-keys"])


class MasterCredentialRequest(BaseModel):
    provider: str
    category: Optional[str] = "llm"
    credentials: Optional[Dict[str, Any]] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    display_name: Optional[str] = None
    is_enabled: bool = True
    is_active: Optional[bool] = None


class MasterCredentialResponse(BaseModel):
    provider: str
    category: str
    is_enabled: bool = True
    is_active: bool = True
    health_status: str = "active"
    status: str = "active"
    last_tested_at: Optional[str] = None
    has_credentials: bool = True
    api_key_masked: Optional[str] = None


class TestConnectionRequest(BaseModel):
    provider: str
    api_key: Optional[str] = None


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[float] = None


@router.get("", response_model=List[MasterCredentialResponse])
async def list_master_keys(_user=Depends(get_superuser)):
    """List all configured master credentials with health and masked status."""
    records = await kodewaves_db_client.list_master_credentials()
    results = []
    for r in records:
        if r.provider.lower() in ("speaches", "ollama"):
            continue
        masked = None
        if r.credentials_encrypted:
            try:
                dec = await master_credential_service.get_decrypted_credential(r.provider)
                if dec:
                    raw_k = dec.get("api_key") or dec.get("key") or dec.get("auth_token") or ""
                    if raw_k:
                        masked = f"••••••••{raw_k[-4:]}" if len(raw_k) > 4 else "••••••••"
                    else:
                        masked = "•••••••• (configured)"
            except Exception:
                masked = "•••••••• (configured)"
        results.append(
            MasterCredentialResponse(
                provider=r.provider,
                category=r.category,
                is_enabled=r.is_enabled,
                is_active=r.is_enabled,
                health_status=r.health_status,
                status=r.health_status,
                last_tested_at=r.last_tested_at.isoformat() if r.last_tested_at else None,
                has_credentials=bool(r.credentials_encrypted),
                api_key_masked=masked,
            )
        )
    return results


@router.post("", response_model=Dict[str, Any])
async def save_master_key(req: MasterCredentialRequest, _user=Depends(get_superuser)):
    """Encrypt and save master credentials for a provider with AES-256 Fernet."""
    creds = dict(req.credentials) if req.credentials else {}
    if req.api_key:
        creds["api_key"] = req.api_key.strip()
    if req.api_secret:
        creds["api_secret"] = req.api_secret.strip()

    category = req.category or "llm"
    is_enabled = req.is_enabled if req.is_active is None else req.is_active

    provider_clean = req.provider.lower().strip()

    success = await master_credential_service.save_master_credential(
        provider=provider_clean,
        category=category.lower().strip(),
        credentials_dict=creds,
        is_enabled=is_enabled,
    )

    # If saving gemini or google, ensure both aliases resolve seamlessly
    if provider_clean in ("gemini", "google"):
        alias = "google" if provider_clean == "gemini" else "gemini"
        await master_credential_service.save_master_credential(
            provider=alias,
            category=category.lower().strip(),
            credentials_dict=creds,
            is_enabled=is_enabled,
        )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to encrypt and store master credentials.")

    try:
        await kodewaves_db_client.record_audit_log(
            actor_id=_user.id,
            actor_email=_user.email,
            action="master_key.upsert",
            resource_type="credential",
            resource_id=provider_clean,
            changes={"is_enabled": is_enabled, "category": category},
        )
    except Exception:
        pass

    return {"message": f"Successfully stored master credentials for {req.provider}"}


@router.post("/test", response_model=TestConnectionResponse)
async def test_master_key_post(req: TestConnectionRequest, _user=Depends(get_superuser)):
    """Perform live connectivity check to upstream provider (via JSON body)."""
    start_time = datetime.now(UTC)
    success, message = await master_credential_service.test_connection(req.provider)
    latency = round((datetime.now(UTC) - start_time).total_seconds() * 1000, 1)

    status_str = "healthy" if success else "invalid"
    # Update health status in DB
    try:
        await kodewaves_db_client.upsert_master_credential(
            provider=req.provider.lower().strip(),
            category="llm",
            credentials_encrypted="",
            is_enabled=True,
            health_status=status_str,
        )
    except Exception:
        pass

    return TestConnectionResponse(success=success, message=message, latency_ms=latency)


@router.post("/{provider}/test", response_model=TestConnectionResponse)
async def test_master_key_connection_path(provider: str, _user=Depends(get_superuser)):
    """Perform live connectivity check to upstream provider (via path param)."""
    start_time = datetime.now(UTC)
    success, message = await master_credential_service.test_connection(provider)
    latency = round((datetime.now(UTC) - start_time).total_seconds() * 1000, 1)

    status_str = "healthy" if success else "invalid"
    try:
        await kodewaves_db_client.upsert_master_credential(
            provider=provider.lower().strip(),
            category="llm",
            credentials_encrypted="",
            is_enabled=True,
            health_status=status_str,
        )
    except Exception:
        pass

    return TestConnectionResponse(success=success, message=message, latency_ms=latency)


@router.delete("/{provider}", response_model=Dict[str, Any])
async def delete_master_key(provider: str, _user=Depends(get_superuser)):
    """Disable or remove master credential for a provider."""
    async with kodewaves_db_client.get_session() as session:
        from sqlalchemy import select
        stmt = select(PlatformMasterCredentialModel).where(
            PlatformMasterCredentialModel.provider == provider.lower().strip()
        )
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail=f"Master credential for '{provider}' not found")

        await session.delete(record)
        await session.commit()
        try:
            await kodewaves_db_client.record_audit_log(
                actor_id=_user.id,
                actor_email=_user.email,
                action="master_key.delete",
                resource_type="credential",
                resource_id=provider,
                changes={"deleted": True},
            )
        except Exception:
            pass
        return {"message": f"Successfully removed master credentials for '{provider}'"}
