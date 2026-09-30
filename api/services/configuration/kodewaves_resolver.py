from typing import Optional
from fastapi import HTTPException
from loguru import logger

from api.db.kodewaves_client import kodewaves_db_client
from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
from api.services.configuration.registry import (
    CartesiaTTSConfiguration,
    DeepgramSTTConfiguration,
    ElevenlabsTTSConfiguration,
    GoogleGeminiSTTConfiguration,
    GoogleGeminiTTSConfiguration,
    GoogleLLMService,
    GroqLLMService,
    NavanaSTTConfiguration,
    NavanaTTSConfiguration,
    OpenAILLMService,
    OpenAISTTConfiguration,
    OpenAITTSService,
    SarvamLLMConfiguration,
    SarvamSTTConfiguration,
    SarvamTTSConfiguration,
    ServiceProviders,
    SpeachesLLMConfiguration,
    SpeachesSTTConfiguration,
    SpeachesTTSConfiguration,
)
from api.services.credentials.master_credential_service import master_credential_service


def _build_master_llm(prov: str, model: str, api_key: str, base_url: Optional[str] = None):
    prov_lower = prov.lower()
    if prov_lower == "openai":
        kwargs = {"api_key": api_key, "model": model}
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAILLMService(**kwargs)
    elif prov_lower == "sarvam":
        return SarvamLLMConfiguration(api_key=api_key, model=model)
    elif prov_lower == "groq":
        return GroqLLMService(api_key=api_key, model=model)
    elif prov_lower in ("google", "gemini"):
        return GoogleLLMService(api_key=api_key, model=model)
    return OpenAILLMService(api_key=api_key, model=model)


def _build_master_stt(prov: str, model: str, api_key: str):
    prov_lower = prov.lower()
    if prov_lower == "deepgram":
        return DeepgramSTTConfiguration(api_key=api_key, model=model)
    elif prov_lower == "navana":
        return NavanaSTTConfiguration(api_key=api_key, model=model)
    elif prov_lower in ("google", "gemini"):
        return GoogleGeminiSTTConfiguration(api_key=api_key, model=model)
    elif prov_lower == "sarvam":
        return SarvamSTTConfiguration(api_key=api_key, model=model)
    elif prov_lower == "openai":
        return OpenAISTTConfiguration(api_key=api_key, model=model)
    return DeepgramSTTConfiguration(api_key=api_key, model=model)


def _build_master_tts(prov: str, model: str, api_key: str, voice: Optional[str] = None):
    prov_lower = prov.lower()
    if prov_lower == "cartesia":
        v = voice if (voice and voice != "default") else "3faa81ae-d3d8-4ab1-9e44-e50e46d33c30"
        return CartesiaTTSConfiguration(api_key=api_key, model=model or "sonic-3.5", voice=v)
    elif prov_lower == "navana":
        v = voice if (voice and voice != "default") else "default_female"
        return NavanaTTSConfiguration(api_key=api_key, model=model or "bodhi-tts-v1", voice=v)
    elif prov_lower in ("google", "gemini"):
        v = voice if (voice and voice != "default") else "Puck"
        return GoogleGeminiTTSConfiguration(api_key=api_key, model=model or "gemini-2.5-flash-preview-tts", voice=v)
    elif prov_lower == "elevenlabs":
        v = voice if (voice and voice != "default") else "21m00Tcm4TlvDq8ikWAM"
        return ElevenlabsTTSConfiguration(api_key=api_key, voice=v)
    elif prov_lower == "sarvam":
        v = voice if (voice and voice != "default") else "meera"
        return SarvamTTSConfiguration(api_key=api_key, voice=v)
    elif prov_lower == "openai":
        v = voice if (voice and voice != "default") else "alloy"
        return OpenAITTSService(api_key=api_key, voice=v)
    v = voice if (voice and voice != "default") else "3faa81ae-d3d8-4ab1-9e44-e50e46d33c30"
    return CartesiaTTSConfiguration(api_key=api_key, voice=v)


async def _resolve_master_llm(effective: EffectiveAIModelConfiguration) -> bool:
    """Resolve sovereign LLM master credentials (Gemini, OpenAI, Sarvam, Groq)."""
    providers_priority = [
        ("gemini", "gemini-2.5-flash"),
        ("google", "gemini-2.5-flash"),
        ("openai", "gpt-4o-mini"),
        ("sarvam", "sarvam-2b"),
        ("groq", "llama-3.3-70b-versatile"),
    ]
    for prov, default_model in providers_priority:
        creds = await master_credential_service.get_master_credential(prov)
        if creds and creds.get("api_key"):
            effective.llm = _build_master_llm(prov, default_model, creds["api_key"], creds.get("base_url"))
            logger.info(f"[KodewavesResolver] Injected master LLM: {prov}/{default_model}")
            return True
    return False


async def _resolve_master_stt(effective: EffectiveAIModelConfiguration) -> bool:
    """Resolve sovereign STT master credentials (Deepgram, Navana, Gemini, Sarvam, OpenAI)."""
    providers_priority = [
        ("deepgram", "nova-3-general"),
        ("navana", "hi-banking-v2-8khz"),
        ("gemini", "gemini-3.5-transcribe"),
        ("google", "gemini-3.5-transcribe"),
        ("sarvam", "saarika:v1"),
        ("openai", "whisper-1"),
    ]
    for prov, default_model in providers_priority:
        creds = await master_credential_service.get_master_credential(prov)
        if creds and creds.get("api_key"):
            effective.stt = _build_master_stt(prov, default_model, creds["api_key"])
            logger.info(f"[KodewavesResolver] Injected master STT: {prov}/{default_model}")
            return True
    return False


async def _resolve_master_tts(effective: EffectiveAIModelConfiguration) -> bool:
    """Resolve sovereign TTS master credentials (Cartesia, Navana, Gemini, ElevenLabs, Sarvam, OpenAI)."""
    providers_priority = [
        ("cartesia", "sonic-3.5", "3faa81ae-d3d8-4ab1-9e44-e50e46d33c30"),
        ("navana", "bodhi-tts-v1", "default_female"),
        ("gemini", "gemini-2.5-flash-preview-tts", "Puck"),
        ("google", "gemini-2.5-flash-preview-tts", "Puck"),
        ("elevenlabs", "eleven_flash_v2_5", "21m00Tcm4TlvDq8ikWAM"),
        ("sarvam", "bulbul:v1", "meera"),
        ("openai", "tts-1", "alloy"),
    ]
    for prov, default_model, fallback_voice in providers_priority:
        creds = await master_credential_service.get_master_credential(prov)
        if creds and creds.get("api_key"):
            current_voice = getattr(effective.tts, "voice", None)
            voice = current_voice if (current_voice and current_voice != "default") else fallback_voice
            effective.tts = _build_master_tts(prov, default_model, creds["api_key"], voice)
            logger.info(f"[KodewavesResolver] Injected master TTS: {prov}/{default_model}")
            return True
    return False


async def apply_kodewaves_sovereign_resolution(
    effective: EffectiveAIModelConfiguration,
    organization_id: Optional[int] = None,
) -> EffectiveAIModelConfiguration:
    """
    Seamlessly injects Kodewaves Superadmin master keys when organization is in
    Platform-Managed mode or lacks provider credentials, severing any external Dograh cloud dependency.

    Guarantees:
    - If Admin BYOK policy is enabled and user has personal keys, user keys are preserved.
    - If user is in Managed Voice mode or lacks personal keys, Admin Master Keys are injected.
    - When provider == 'dograh', replaces with active master provider (OpenAI, Deepgram, Cartesia/ElevenLabs).
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
    local_engine = await kodewaves_db_client.get_setting("local_ai") or await kodewaves_db_client.get_setting("local_ai_engine")
    engine_enabled = (
        local_engine.get("enable_local_ai_engine", local_engine.get("enabled", True))
        if local_engine else True
    )
    access_policy = local_engine.get("local_ai_access_policy", local_engine.get("access_policy", "public")) if local_engine else "public"
    is_public_local_ai = (access_policy == "public")
    org_access = await kodewaves_db_client.get_setting(f"local_ai_org_{organization_id}")
    has_local_access = is_public_local_ai or (bool(org_access.get("enabled", False)) if org_access else False)

    ollama_base = local_engine.get("ollama_endpoint", local_engine.get("ollama_url", "http://ollama:11434")) if local_engine else "http://ollama:11434"
    ollama_v1_url = ollama_base if ollama_base.endswith("/v1") else f"{ollama_base.rstrip('/')}/v1"
    speaches_base = local_engine.get("speaches_endpoint", local_engine.get("speaches_url", "http://speaches:8000")) if local_engine else "http://speaches:8000"
    speaches_v1_url = speaches_base if speaches_base.endswith("/v1") else f"{speaches_base.rstrip('/')}/v1"

    is_using_local_cpu_engine = False

    if effective.llm:
        provider = getattr(effective.llm, "provider", "openai")
        provider_name = getattr(provider, "value", provider)
        user_key = getattr(effective.llm, "api_key", None)

        if str(provider_name).lower() == "speaches" or user_key == "sovereign-local-cpu":
            if not engine_enabled or not has_local_access:
                logger.warning(f"[KodewavesResolver] Org {organization_id} attempted to use Local AI Engine without admin permission")
                raise HTTPException(
                    status_code=403,
                    detail="Local CPU AI Engine access is restricted. Please contact your administrator to enable access.",
                )
            effective.llm = SpeachesLLMConfiguration(
                api_key="local-cpu-token",
                model="qwen2.5:0.5b",
                base_url=ollama_v1_url,
            )
            is_using_local_cpu_engine = True
        elif str(provider_name).lower() in ("dograh", "default") or not allow_byok or not user_key or user_key == "sovereign-managed":
            if str(provider_name).lower() in ("dograh", "default"):
                resolved = await _resolve_master_llm(effective)
                if resolved:
                    is_using_master_keys = True
                else:
                    # Automatic graceful fallback to Local CPU Ollama when no cloud keys exist
                    logger.info(f"[KodewavesResolver] No cloud master LLM key configured; falling back to Local CPU Ollama for Org {organization_id}")
                    effective.llm = SpeachesLLMConfiguration(
                        api_key="local-cpu-token",
                        model="qwen2.5:0.5b",
                        base_url=ollama_v1_url,
                    )
                    is_using_local_cpu_engine = True
            else:
                master_creds = await master_credential_service.get_master_credential(str(provider_name))
                if master_creds and master_creds.get("api_key"):
                    effective.llm.api_key = master_creds["api_key"]
                    if master_creds.get("base_url") and hasattr(effective.llm, "base_url"):
                        effective.llm.base_url = master_creds["base_url"]
                    is_using_master_keys = True

    # 4. Resolve STT Section
    if effective.stt:
        provider = getattr(effective.stt, "provider", "deepgram")
        provider_name = getattr(provider, "value", provider)
        user_key = getattr(effective.stt, "api_key", None)

        if str(provider_name).lower() == "speaches" or user_key == "sovereign-local-cpu":
            if not engine_enabled or not has_local_access:
                raise HTTPException(
                    status_code=403,
                    detail="Local CPU AI Engine access is restricted. Please contact your administrator to enable access.",
                )
            effective.stt = SpeachesSTTConfiguration(
                api_key="local-cpu-token",
                model="Systran/faster-whisper-tiny",
                base_url=speaches_v1_url,
            )
            is_using_local_cpu_engine = True
        elif str(provider_name).lower() in ("dograh", "default") or not allow_byok or not user_key or user_key == "sovereign-managed":
            if str(provider_name).lower() in ("dograh", "default"):
                resolved = await _resolve_master_stt(effective)
                if resolved:
                    is_using_master_keys = True
                else:
                    # Automatic graceful fallback to Local CPU Speaches Whisper STT
                    logger.info(f"[KodewavesResolver] No cloud master STT key configured; falling back to Local CPU Speaches STT for Org {organization_id}")
                    effective.stt = SpeachesSTTConfiguration(
                        api_key="local-cpu-token",
                        model="Systran/faster-whisper-tiny",
                        base_url=speaches_v1_url,
                    )
                    is_using_local_cpu_engine = True
            else:
                master_creds = await master_credential_service.get_master_credential(str(provider_name))
                if master_creds and master_creds.get("api_key"):
                    effective.stt.api_key = master_creds["api_key"]
                    is_using_master_keys = True

    # 5. Resolve TTS Section
    if effective.tts:
        provider = getattr(effective.tts, "provider", "elevenlabs")
        provider_name = getattr(provider, "value", provider)
        user_key = getattr(effective.tts, "api_key", None)

        if str(provider_name).lower() == "speaches" or user_key == "sovereign-local-cpu":
            if not engine_enabled or not has_local_access:
                raise HTTPException(
                    status_code=403,
                    detail="Local CPU AI Engine access is restricted. Please contact your administrator to enable access.",
                )
            current_voice = getattr(effective.tts, "voice", "af_heart")
            voice = current_voice if (current_voice and not current_voice.startswith("dg_") and current_voice != "default") else "af_heart"
            effective.tts = SpeachesTTSConfiguration(
                api_key="local-cpu-token",
                model="kokoro",
                voice=voice,
                base_url=speaches_v1_url,
            )
            is_using_local_cpu_engine = True
        elif str(provider_name).lower() in ("dograh", "default") or not allow_byok or not user_key or user_key == "sovereign-managed":
            if str(provider_name).lower() in ("dograh", "default"):
                resolved = await _resolve_master_tts(effective)
                if resolved:
                    is_using_master_keys = True
                else:
                    # Automatic graceful fallback to Local CPU Speaches Kokoro TTS
                    logger.info(f"[KodewavesResolver] No cloud master TTS key configured; falling back to Local CPU Speaches Kokoro TTS for Org {organization_id}")
                    current_voice = getattr(effective.tts, "voice", "af_heart")
                    voice = current_voice if (current_voice and not current_voice.startswith("dg_") and current_voice != "default") else "af_heart"
                    effective.tts = SpeachesTTSConfiguration(
                        api_key="local-cpu-token",
                        model="kokoro",
                        voice=voice,
                        base_url=speaches_v1_url,
                    )
                    is_using_local_cpu_engine = True
            else:
                master_creds = await master_credential_service.get_master_credential(str(provider_name))
                if master_creds and master_creds.get("api_key"):
                    effective.tts.api_key = master_creds["api_key"]
                    is_using_master_keys = True


    # 6. Resolve Realtime / Speech-to-Speech Section
    if effective.is_realtime and effective.realtime:
        provider = getattr(effective.realtime, "provider", "openai")
        provider_name = getattr(provider, "value", provider)
        user_key = getattr(effective.realtime, "api_key", None)

        if not allow_byok or not user_key or user_key == "sovereign-managed":
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
