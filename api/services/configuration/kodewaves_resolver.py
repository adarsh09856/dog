from typing import Optional
from fastapi import HTTPException
from loguru import logger

from api.db.kodewaves_client import kodewaves_db_client
from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
from api.services.credentials.master_credential_service import master_credential_service


async def apply_kodewaves_sovereign_resolution(
    effective: EffectiveAIModelConfiguration,
    organization_id: Optional[int] = None,
) -> EffectiveAIModelConfiguration:
    """
    Seamlessly injects Kodewaves Superadmin master keys when organization is in
    Platform-Managed mode or lacks provider credentials, severing the api.dograh.com dependency.

    Guarantees:
    - If Admin BYOK policy is enabled and user has personal keys, user keys are preserved.
    - If user lacks personal keys or Admin BYOK policy is disabled, Admin Master Keys are injected.
    - Verifies local organization wallet minute balance before execution.
    - Pipecat receives the exact typed EffectiveAIModelConfiguration it expects with zero code changes.
    """
    if organization_id is None:
        return effective

    # 1. Check Admin Global BYOK Policy
    byok_policy = await kodewaves_db_client.get_setting("byok_policy")
    allow_byok = byok_policy.get("allow_user_byok", True) if byok_policy else True

    # 2. Check Wallet Minute Balance
    wallet = await kodewaves_db_client.get_or_create_wallet(organization_id)
    has_positive_balance = (wallet.credit_balance_minutes + wallet.bonus_minutes) > 0

    is_using_master_keys = False

    # 3. Resolve LLM Section
    if effective.llm:
        provider = getattr(effective.llm, "provider", "openai")
        provider_name = getattr(provider, "value", provider)
        user_key = getattr(effective.llm, "api_key", None)

        if not allow_byok or not user_key:
            master_creds = await master_credential_service.get_master_credential(str(provider_name))
            if master_creds and master_creds.get("api_key"):
                effective.llm.api_key = master_creds["api_key"]
                if master_creds.get("base_url") and hasattr(effective.llm, "base_url"):
                    effective.llm.base_url = master_creds["base_url"]
                is_using_master_keys = True

    # 4. Resolve TTS Section
    if effective.tts:
        provider = getattr(effective.tts, "provider", "elevenlabs")
        provider_name = getattr(provider, "value", provider)
        user_key = getattr(effective.tts, "api_key", None)

        if not allow_byok or not user_key:
            master_creds = await master_credential_service.get_master_credential(str(provider_name))
            if master_creds and master_creds.get("api_key"):
                effective.tts.api_key = master_creds["api_key"]
                is_using_master_keys = True

    # 5. Resolve STT Section
    if effective.stt:
        provider = getattr(effective.stt, "provider", "deepgram")
        provider_name = getattr(provider, "value", provider)
        user_key = getattr(effective.stt, "api_key", None)

        if not allow_byok or not user_key:
            master_creds = await master_credential_service.get_master_credential(str(provider_name))
            if master_creds and master_creds.get("api_key"):
                effective.stt.api_key = master_creds["api_key"]
                is_using_master_keys = True

    # 6. Resolve Realtime / Speech-to-Speech Section
    if effective.is_realtime and effective.realtime:
        provider = getattr(effective.realtime, "provider", "openai")
        provider_name = getattr(provider, "value", provider)
        user_key = getattr(effective.realtime, "api_key", None)

        if not allow_byok or not user_key:
            master_creds = await master_credential_service.get_master_credential(str(provider_name))
            if master_creds and master_creds.get("api_key"):
                effective.realtime.api_key = master_creds["api_key"]
                is_using_master_keys = True

    # 7. Balance Enforcement for Platform-Managed Calls
    if is_using_master_keys and not has_positive_balance:
        logger.warning(f"[KodewavesResolver] Org {organization_id} has depleted voice balance ({wallet.credit_balance_minutes} min)")
        raise HTTPException(
            status_code=402,
            detail="Your organization has zero voice credits. Please purchase a minute top-up package to continue.",
        )

    return effective
