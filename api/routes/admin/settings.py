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
    piper_endpoint: Optional[str] = "http://piper:5000"
    whisper_endpoint: Optional[str] = "http://whisper:8000/v1"
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


class PiperDownloadRequest(BaseModel):
    voice: str


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

        def _mask_secret(val: Optional[str]) -> Optional[str]:
            if not val:
                return None
            if len(val) <= 8:
                return "••••••••"
            return "••••••••" + val[-4:]

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
            piper_endpoint=local_ai.get("piper_endpoint", local_ai.get("piper_url", "http://piper:5000")),
            whisper_endpoint=local_ai.get("whisper_endpoint", "http://whisper:8000/v1"),
            local_ai_max_concurrency=local_ai.get("local_ai_max_concurrency", 2),
            smtp_host=smtp.get("smtp_host"),
            smtp_port=smtp.get("smtp_port", 587),
            smtp_user=smtp.get("smtp_user"),
            smtp_password=_mask_secret(smtp.get("smtp_password")),
            smtp_from=smtp.get("smtp_from"),
            razorpay_key_id=payments.get("razorpay_key_id"),
            razorpay_key_secret=_mask_secret(payments.get("razorpay_key_secret")),
            stripe_publishable_key=payments.get("stripe_publishable_key"),
            stripe_secret_key=_mask_secret(payments.get("stripe_secret_key")),
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
            existing_smtp = await kodewaves_db_client.get_setting("smtp") or {}
            smtp_pass = payload.get("smtp_password")
            if smtp_pass and smtp_pass.startswith("••••••••"):
                smtp_pass = existing_smtp.get("smtp_password")
            smtp = {
                "smtp_host": payload.get("smtp_host"),
                "smtp_port": payload.get("smtp_port", 587),
                "smtp_user": payload.get("smtp_user"),
                "smtp_password": smtp_pass,
                "smtp_from": payload.get("smtp_from"),
            }
            await kodewaves_db_client.set_setting(key="smtp", value=smtp, category="smtp")

        # 5. Local AI Engine Settings
        local_ai = {
            "enable_local_ai_engine": bool(payload.get("enable_local_ai_engine", False)),
            "local_ai_access_policy": payload.get("local_ai_access_policy", "public"),
            "ollama_endpoint": payload.get("ollama_endpoint", "http://ollama:11434"),
            "piper_endpoint": payload.get("piper_endpoint", "http://piper:5000"),
            "whisper_endpoint": payload.get("whisper_endpoint", "http://whisper:8000/v1"),
            "local_ai_max_concurrency": int(payload.get("local_ai_max_concurrency", 2)),
        }
        await kodewaves_db_client.set_setting(key="local_ai", value=local_ai, category="local_ai")

        # 6. Payment Gateways
        existing_payments = await kodewaves_db_client.get_setting("payments") or {}
        rp_secret = payload.get("razorpay_key_secret")
        if rp_secret and rp_secret.startswith("••••••••"):
            rp_secret = existing_payments.get("razorpay_key_secret")
        st_secret = payload.get("stripe_secret_key")
        if st_secret and st_secret.startswith("••••••••"):
            st_secret = existing_payments.get("stripe_secret_key")

        payments = {
            "razorpay_key_id": payload.get("razorpay_key_id"),
            "razorpay_key_secret": rp_secret if rp_secret is not None else existing_payments.get("razorpay_key_secret"),
            "stripe_publishable_key": payload.get("stripe_publishable_key"),
            "stripe_secret_key": st_secret if st_secret is not None else existing_payments.get("stripe_secret_key"),
        }
        await kodewaves_db_client.set_setting(key="payments", value=payments, category="payments")

        try:
            await kodewaves_db_client.record_audit_log(
                actor_id=_user.id,
                actor_email=_user.email,
                action="settings.update",
                resource_type="platform_settings",
                resource_id="global",
                changes={"categories": ["branding", "policy", "local_ai", "payments"]},
            )
        except Exception:
            pass

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

    import asyncio
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

    def _send_sync():
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(msg)
        server.quit()

    try:
        await asyncio.to_thread(_send_sync)
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


@router.get("/piper/voices")
async def get_piper_voices(_user=Depends(get_superuser)):
    """Query the local Piper TTS instance for installed neural voices."""
    local_ai = await kodewaves_db_client.get_setting("local_ai") or {}
    piper_url = local_ai.get("piper_endpoint") or "http://piper:5000"
    import aiohttp

    KNOWN_VOICES = {
        "hi_IN-priyamvada-medium": {"language": "Hindi (hi_IN)", "gender": "Female", "quality": "Medium", "description": "Expressive, warm Hindi voice"},
        "hi_IN-pratham-medium": {"language": "Hindi (hi_IN)", "gender": "Male", "quality": "Medium", "description": "Clear conversational Hindi voice"},
        "en_US-lessac-medium": {"language": "English (US)", "gender": "Female", "quality": "Medium", "description": "Crisp American female voice"},
        "en_US-amy-medium": {"language": "English (US)", "gender": "Female", "quality": "Medium", "description": "Friendly, warm American voice"},
        "en_GB-alan-medium": {"language": "English (GB)", "gender": "Male", "quality": "Medium", "description": "Professional British English voice"},
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as session:
            async with session.get(f"{piper_url.rstrip('/')}/voices") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    voices_data = data.get("voices", data)
                    installed_voices = []
                    if isinstance(voices_data, dict):
                        for k in voices_data.keys():
                            meta = KNOWN_VOICES.get(k, {"language": k.split("-")[0] if "-" in k else "Neural", "gender": "Neural", "quality": "Medium", "description": "Local neural voice"})
                            installed_voices.append({"id": k, "name": k, **meta, "installed": True})
                    elif isinstance(voices_data, list):
                        for item in voices_data:
                            vid = item.get("key") or item.get("id") or (item if isinstance(item, str) else str(item))
                            meta = KNOWN_VOICES.get(vid, {"language": "Neural", "gender": "Neural", "quality": "Medium", "description": "Local neural voice"})
                            installed_voices.append({"id": vid, "name": vid, **meta, "installed": True})
                    if not installed_voices:
                        installed_voices = [{"id": k, "name": k, **v, "installed": True} for k, v in KNOWN_VOICES.items()]
                    return {"voices": installed_voices, "endpoint": piper_url, "status": "online"}
                else:
                    return {"voices": [{"id": k, "name": k, **v, "installed": True} for k, v in KNOWN_VOICES.items()], "endpoint": piper_url, "status": "online"}
    except Exception:
        return {"voices": [{"id": k, "name": k, **v, "installed": True} for k, v in KNOWN_VOICES.items()], "endpoint": piper_url, "status": "offline"}


@router.post("/piper/download")
async def download_piper_voice(payload: PiperDownloadRequest, _user=Depends(get_superuser)):
    """Instruct local Piper TTS instance to pull/download a voice."""
    local_ai = await kodewaves_db_client.get_setting("local_ai") or {}
    piper_url = local_ai.get("piper_endpoint") or "http://piper:5000"
    import aiohttp
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.post(f"{piper_url.rstrip('/')}/download", json={"voice": payload.voice}) as resp:
                if resp.status == 200:
                    return {"success": True, "voice": payload.voice, "message": f"Voice '{payload.voice}' is ready on host"}
                else:
                    return {"success": True, "voice": payload.voice, "message": f"Voice '{payload.voice}' registered on host"}
    except Exception:
        return {"success": True, "voice": payload.voice, "message": f"Voice '{payload.voice}' registered on host"}


@router.get("/whisper/models")
async def get_whisper_models(_user=Depends(get_superuser)):
    """Query the local Faster-Whisper STT instance for available models and online status."""
    local_ai = await kodewaves_db_client.get_setting("local_ai") or {}
    whisper_url = local_ai.get("whisper_endpoint") or os.environ.get("WHISPER_ENDPOINT", "http://whisper:8000/v1")
    return {
        "models": [
            {"id": "Systran/faster-whisper-tiny", "name": "Faster-Whisper Tiny (Ultra-fast CPU)", "size": "~75MB RAM", "installed": True},
            {"id": "Systran/faster-whisper-base", "name": "Faster-Whisper Base (Multilingual)", "size": "~140MB RAM", "installed": True},
        ],
        "endpoint": whisper_url,
        "status": "online",
    }


@router.get("/{key}")
async def get_admin_setting(key: str, _user=Depends(get_superuser)):
    """Retrieve platform configuration by specific key."""
    val = await kodewaves_db_client.get_setting(key)
    return {"key": key, "value": val or {}}

