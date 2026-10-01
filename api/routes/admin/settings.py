from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import GlobalPlatformSettingModel
from api.services.auth.depends import get_superuser

router = APIRouter(prefix="/settings", tags=["admin-settings"])


class PlatformSettingsResponse(BaseModel):
    company_name: str = "Kodewaves"
    logo_url: Optional[str] = "/kodewaves-logo.png"
    support_email: Optional[str] = "support@kodewaves.in"
    primary_color: Optional[str] = "#4f46e5"
    allow_user_byok: bool = False
    enforce_wallet_balance: bool = True
    enable_local_ai_engine: bool = False
    local_ai_access_policy: str = "public"  # 'public' (all users) or 'restricted' (per-user grant)
    ollama_endpoint: Optional[str] = "http://ollama:11434"
    speaches_endpoint: Optional[str] = "http://speaches:8000/v1"
    local_ai_max_concurrency: Optional[int] = 2
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    razorpay_key_id: Optional[str] = None
    razorpay_key_secret: Optional[str] = None
    stripe_publishable_key: Optional[str] = None
    stripe_secret_key: Optional[str] = None


class TestEmailRequest(BaseModel):
    recipient_email: str


class OllamaPullRequest(BaseModel):
    model: str


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
        local_ai = settings_map.get("local_ai") or settings_map.get("local_ai_engine") or {}
        smtp = settings_map.get("smtp") or {}
        payments = settings_map.get("payments") or {}

        return PlatformSettingsResponse(
            company_name=branding.get("company_name", "Kodewaves"),
            logo_url=branding.get("logo_url", "/kodewaves-logo.png"),
            support_email=branding.get("support_email", "support@kodewaves.in"),
            primary_color=branding.get("primary_color", "#4f46e5"),
            allow_user_byok=byok.get("allow_user_byok", False),
            enforce_wallet_balance=wallet.get("enforce_wallet_balance", True),
            enable_local_ai_engine=local_ai.get("enable_local_ai_engine", local_ai.get("enabled", False)),
            local_ai_access_policy=local_ai.get("local_ai_access_policy", local_ai.get("access_policy", "public")),
            ollama_endpoint=local_ai.get("ollama_endpoint", local_ai.get("ollama_url", "http://ollama:11434")),
            speaches_endpoint=local_ai.get("speaches_endpoint", local_ai.get("speaches_url", "http://speaches:8000/v1")),
            local_ai_max_concurrency=local_ai.get("local_ai_max_concurrency", 2),
            smtp_host=smtp.get("smtp_host"),
            smtp_port=smtp.get("smtp_port", 587),
            smtp_user=smtp.get("smtp_user"),
            smtp_password=smtp.get("smtp_password"),
            smtp_from=smtp.get("smtp_from"),
            razorpay_key_id=payments.get("razorpay_key_id"),
            razorpay_key_secret=payments.get("razorpay_key_secret"),
            stripe_publishable_key=payments.get("stripe_publishable_key"),
            stripe_secret_key=payments.get("stripe_secret_key"),
        )


@router.post("")
async def update_platform_settings(payload: Dict[str, Any], _user=Depends(get_superuser)):
    """Update global platform configuration (Branding, BYOK policy, SMTP, Payments, Local AI)."""
    # If standard PlatformSettings dictionary is submitted:
    if "company_name" in payload or "allow_user_byok" in payload or "smtp_host" in payload or "enable_local_ai_engine" in payload or "razorpay_key_id" in payload:
        # 1. Branding
        branding = {
            "company_name": payload.get("company_name", "Kodewaves"),
            "logo_url": payload.get("logo_url", "/kodewaves-logo.png"),
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
                "smtp_password": payload.get("smtp_password"),
                "smtp_from": payload.get("smtp_from"),
            }
            await kodewaves_db_client.set_setting(key="smtp", value=smtp, category="smtp")

        # 5. Local AI Engine Settings
        local_ai = {
            "enable_local_ai_engine": bool(payload.get("enable_local_ai_engine", False)),
            "local_ai_access_policy": payload.get("local_ai_access_policy", "public"),
            "ollama_endpoint": payload.get("ollama_endpoint", "http://ollama:11434"),
            "speaches_endpoint": payload.get("speaches_endpoint", "http://speaches:8000/v1"),
            "local_ai_max_concurrency": int(payload.get("local_ai_max_concurrency", 2)),
        }
        await kodewaves_db_client.set_setting(key="local_ai", value=local_ai, category="local_ai")

        # 6. Payment Gateways
        payments = {
            "razorpay_key_id": payload.get("razorpay_key_id"),
            "razorpay_key_secret": payload.get("razorpay_key_secret"),
            "stripe_publishable_key": payload.get("stripe_publishable_key"),
            "stripe_secret_key": payload.get("stripe_secret_key"),
        }
        await kodewaves_db_client.set_setting(key="payments", value=payments, category="payments")

        return {"message": "Successfully saved sovereign platform settings"}

    # Fallback to key-value update if structured as { category, key, value }
    key = payload.get("key")
    value = payload.get("value")
    category = payload.get("category", "general")
    if key and value is not None:
        await kodewaves_db_client.set_setting(key=key, value=value, category=category)
        return {"message": f"Successfully updated setting '{key}'"}

    return {"message": "Settings updated"}


@router.post("/test-email")
async def send_test_email(payload: TestEmailRequest, _user=Depends(get_superuser)):
    """Send a test email using configured SMTP platform settings."""
    smtp_setting = await kodewaves_db_client.get_setting("smtp") or {}
    host = smtp_setting.get("smtp_host")
    port = int(smtp_setting.get("smtp_port") or 587)
    user = smtp_setting.get("smtp_user")
    password = smtp_setting.get("smtp_password")
    from_email = smtp_setting.get("smtp_from") or user or "noreply@kodewaves.in"

    if not host:
        raise HTTPException(status_code=400, detail="SMTP Host is not configured in Platform Settings")

    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = payload.recipient_email
    msg["Subject"] = "Kodewaves SMTP Test Verification"
    body = (
        "Congratulations! Your Kodewaves SMTP configuration is working perfectly.\n\n"
        f"Server: {host}:{port}\n"
        f"Sender: {from_email}\n"
        "Platform notifications, alerts, and verification emails will be delivered reliably."
    )
    msg.attach(MIMEText(body, "plain"))

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(msg)
        server.quit()
        return {"success": True, "message": f"Test email successfully sent to {payload.recipient_email}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


@router.get("/ollama/models")
async def get_ollama_models(_user=Depends(get_superuser)):
    """Query the local Ollama instance for installed models."""
    local_ai = await kodewaves_db_client.get_setting("local_ai") or {}
    ollama_url = local_ai.get("ollama_endpoint") or "http://ollama:11434"
    import aiohttp
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(f"{ollama_url.rstrip('/')}/api/tags") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {"models": data.get("models", []), "endpoint": ollama_url, "status": "online"}
                else:
                    return {"models": [], "endpoint": ollama_url, "status": f"HTTP {resp.status}"}
    except Exception as e:
        return {"models": [], "endpoint": ollama_url, "status": f"unreachable: {str(e)}"}


@router.post("/ollama/pull")
async def pull_ollama_model(payload: OllamaPullRequest, _user=Depends(get_superuser)):
    """Instruct local Ollama instance to pull/download an AI model."""
    local_ai = await kodewaves_db_client.get_setting("local_ai") or {}
    ollama_url = local_ai.get("ollama_endpoint") or "http://ollama:11434"
    import aiohttp
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
            async with session.post(f"{ollama_url.rstrip('/')}/api/pull", json={"name": payload.model, "stream": False}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {"success": True, "model": payload.model, "result": data}
                else:
                    text = await resp.text()
                    raise HTTPException(status_code=resp.status, detail=f"Ollama pull failed: {text}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to Ollama at {ollama_url}: {str(e)}")


@router.delete("/ollama/models/{model_name:path}")
async def delete_ollama_model(model_name: str, _user=Depends(get_superuser)):
    """Delete an installed model from local Ollama instance."""
    local_ai = await kodewaves_db_client.get_setting("local_ai") or {}
    ollama_url = local_ai.get("ollama_endpoint") or "http://ollama:11434"
    import aiohttp
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.delete(f"{ollama_url.rstrip('/')}/api/delete", json={"name": model_name}) as resp:
                if resp.status == 200:
                    return {"success": True, "message": f"Model {model_name} deleted successfully"}
                else:
                    text = await resp.text()
                    raise HTTPException(status_code=resp.status, detail=f"Ollama delete failed: {text}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to Ollama at {ollama_url}: {str(e)}")


@router.get("/{key}")
async def get_admin_setting(key: str, _user=Depends(get_superuser)):
    """Retrieve platform configuration by specific key."""
    val = await kodewaves_db_client.get_setting(key)
    return {"key": key, "value": val or {}}
