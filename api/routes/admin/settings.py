from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import GlobalPlatformSettingModel
from api.services.auth.depends import get_superuser

router = APIRouter(prefix="/settings", tags=["admin-settings"])


class PlatformSettingsResponse(BaseModel):
    company_name: str = "Kodewaves"
    logo_url: Optional[str] = "/dograh-logo.png"
    support_email: Optional[str] = "support@kodewaves.in"
    primary_color: Optional[str] = "#4f46e5"
    allow_user_byok: bool = False
    enforce_wallet_balance: bool = True
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 587
    smtp_user: Optional[str] = None
    smtp_from: Optional[str] = None


@router.get("", response_model=PlatformSettingsResponse)
async def get_all_platform_settings(_user=Depends(get_superuser)):
    """Retrieve all consolidated sovereign platform settings."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(GlobalPlatformSettingModel)
        result = await session.execute(stmt)
        records = result.scalars().all()

        settings_map: Dict[str, Any] = {}
        for r in records:
            settings_map[r.key] = r.value

        branding = settings_map.get("branding") or {}
        byok = settings_map.get("byok_policy") or {}
        wallet = settings_map.get("wallet_policy") or {}
        smtp = settings_map.get("smtp") or {}

        return PlatformSettingsResponse(
            company_name=branding.get("company_name", "Kodewaves"),
            logo_url=branding.get("logo_url", "/dograh-logo.png"),
            support_email=branding.get("support_email", "support@kodewaves.in"),
            primary_color=branding.get("primary_color", "#4f46e5"),
            allow_user_byok=byok.get("allow_user_byok", False),
            enforce_wallet_balance=wallet.get("enforce_wallet_balance", True),
            smtp_host=smtp.get("smtp_host"),
            smtp_port=smtp.get("smtp_port", 587),
            smtp_user=smtp.get("smtp_user"),
            smtp_from=smtp.get("smtp_from"),
        )


@router.post("")
async def update_platform_settings(payload: Dict[str, Any], _user=Depends(get_superuser)):
    """Update global platform configuration (Branding, BYOK policy, SMTP)."""
    # If standard PlatformSettings dictionary is submitted:
    if "company_name" in payload or "allow_user_byok" in payload or "smtp_host" in payload:
        # 1. Branding
        branding = {
            "company_name": payload.get("company_name", "Kodewaves"),
            "logo_url": payload.get("logo_url", "/dograh-logo.png"),
            "support_email": payload.get("support_email", "support@kodewaves.in"),
            "primary_color": payload.get("primary_color", "#4f46e5"),
        }
        await kodewaves_db_client.set_setting(key="branding", value=branding, category="branding")

        # 2. BYOK Policy
        byok = {
            "allow_user_byok": bool(payload.get("allow_user_byok", False)),
        }
        await kodewaves_db_client.set_setting(key="byok_policy", value=byok, category="policy")

        # 3. Wallet Policy
        wallet = {
            "enforce_wallet_balance": bool(payload.get("enforce_wallet_balance", True)),
        }
        await kodewaves_db_client.set_setting(key="wallet_policy", value=wallet, category="policy")

        # 4. SMTP Settings
        if payload.get("smtp_host"):
            smtp = {
                "smtp_host": payload.get("smtp_host"),
                "smtp_port": payload.get("smtp_port", 587),
                "smtp_user": payload.get("smtp_user"),
                "smtp_from": payload.get("smtp_from"),
            }
            await kodewaves_db_client.set_setting(key="smtp", value=smtp, category="smtp")

        return {"message": "Successfully saved sovereign platform settings"}

    # Fallback to key-value update if structured as { category, key, value }
    key = payload.get("key")
    value = payload.get("value")
    category = payload.get("category", "general")
    if key and value is not None:
        await kodewaves_db_client.set_setting(key=key, value=value, category=category)
        return {"message": f"Successfully updated setting '{key}'"}

    return {"message": "Settings updated"}


@router.get("/{key}")
async def get_admin_setting(key: str, _user=Depends(get_superuser)):
    """Retrieve platform configuration by specific key."""
    val = await kodewaves_db_client.get_setting(key)
    return {"key": key, "value": val or {}}
