import os
from typing import Optional
from fastapi import HTTPException
from loguru import logger

from api.db.kodewaves_client import kodewaves_db_client
from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
from api.services.configuration.registry import (
    AnthropicLLMService,
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
    elif prov_lower == "anthropic":
        return AnthropicLLMService(api_key=api_key, model=model)
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


def _detect_provider_from_llm_model(model: Optional[str]) -> Optional[str]:
    if not model or model == "default":
        return None
    ml = model.lower()
    if ml.startswith("gpt-") or ml.startswith("o1") or ml.startswith("o3"):
        return "openai"
    if ml.startswith("gemini"):
        return "gemini"
    if ml.startswith("claude") or "anthropic" in ml:
        return "anthropic"
    if "sarvam" in ml:
        return "sarvam"
    if "llama" in ml or "groq" in ml:
        return "groq"
    return None


def _detect_provider_from_stt_model(model: Optional[str]) -> Optional[str]:
    if not model or model == "default":
        return None
    ml = model.lower()
    if ml.startswith("nova") or "deepgram" in ml:
        return "deepgram"
    if "whisper" in ml:
        return "openai"
    if "banking" in ml or "navana" in ml:
        return "navana"
    if "saarika" in ml or "saaras" in ml:
        return "sarvam"
    if "gemini" in ml or "google" in ml or "transcribe" in ml:
        return "gemini"
    if "azure" in ml:
        return "azure"
    return None


async def _resolve_master_llm(effective: EffectiveAIModelConfiguration) -> bool:
    """Resolve sovereign LLM master credentials (Gemini, OpenAI, Sarvam, Groq, Anthropic)."""
    current_model = getattr(effective.llm, "model", None)
    detected_prov = _detect_provider_from_llm_model(current_model)

    # 1. If user selected a specific model and matching credentials exist, route directly
    if detected_prov:
        creds = await master_credential_service.get_master_credential(detected_prov)
        if creds and creds.get("api_key"):
            effective.llm = _build_master_llm(detected_prov, current_model, creds["api_key"], creds.get("base_url"))
            logger.info(f"[KodewavesResolver] Injected targeted LLM: {detected_prov}/{current_model}")
            return True

    # 2. Fallback provider priority order
    providers_priority = [
        ("gemini", "gemini-3.8-flash"),
        ("google", "gemini-3.8-flash"),
        ("openai", "gpt-4o-mini"),
        ("anthropic", "claude-3-5-sonnet-20241022"),
        ("sarvam", "sarvam-2b"),
        ("groq", "llama-3.3-70b-versatile"),
    ]
    for prov, default_model in providers_priority:
        creds = await master_credential_service.get_master_credential(prov)
        if creds and creds.get("api_key"):
            model = current_model if (current_model and current_model != "default" and _detect_provider_from_llm_model(current_model) in (None, prov)) else default_model
            effective.llm = _build_master_llm(prov, model, creds["api_key"], creds.get("base_url"))
            logger.info(f"[KodewavesResolver] Injected master LLM: {prov}/{model}")
            return True
    return False


async def _resolve_master_stt(effective: EffectiveAIModelConfiguration) -> bool:
    """Resolve sovereign STT master credentials (Deepgram, Gemini, Navana, Sarvam, OpenAI)."""
    current_model = getattr(effective.stt, "model", None)
    detected_prov = _detect_provider_from_stt_model(current_model)

    # 1. If user selected a specific STT model and matching credentials exist, route directly
    if detected_prov:
        creds = await master_credential_service.get_master_credential(detected_prov)
        if creds and creds.get("api_key"):
            stt_model = "gemini-3.8-flash" if detected_prov in ("gemini", "google") and ("stt" in current_model.lower() or current_model == "default") else current_model
            effective.stt = _build_master_stt(detected_prov, stt_model, creds["api_key"])
            logger.info(f"[KodewavesResolver] Injected targeted STT: {detected_prov}/{stt_model}")
            return True

    # 2. Fallback provider priority order
    providers_priority = [
        ("deepgram", "nova-3-general"),
        ("gemini", "gemini-3.8-flash"),
        ("google", "gemini-3.8-flash"),
        ("navana", "hi-banking-v2-8khz"),
        ("sarvam", "saarika:v1"),
        ("openai", "whisper-1"),
    ]
    for prov, default_model in providers_priority:
        creds = await master_credential_service.get_master_credential(prov)
        if creds and creds.get("api_key"):
            model = current_model if (current_model and current_model != "default" and _detect_provider_from_stt_model(current_model) in (None, prov)) else default_model
            effective.stt = _build_master_stt(prov, model, creds["api_key"])
            logger.info(f"[KodewavesResolver] Injected master STT: {prov}/{model}")
            return True
    return False


def _detect_provider_from_voice(voice: Optional[str]) -> Optional[str]:
    if not voice or voice == "default":
        return None
    vl = voice.lower()
    if vl.startswith(("af_", "am_", "bf_", "bm_", "if_", "im_")):
        return "speaches"
    if vl.startswith("aura-"):
        return "deepgram"
    if vl in ("alloy", "echo", "fable", "onyx", "nova", "shimmer"):
        return "openai"
    if vl in ("journey", "puck", "charon", "aoede", "fenrir", "kore"):
        return "gemini"
    if "neural" in vl or vl.startswith(("en-us-", "en-in-", "hi-in-")):
        return "azure"
    if vl in ("arvind", "amol", "amrita", "ananya", "aditi", "abhinav", "meera"):
        return "sarvam"
    if vl.startswith(("hi-", "te-", "kn-", "mr-")):
        return "navana"
    if vl in ("emily", "arman", "samantha", "raj"):
        return "smallest"
    if len(voice) == 20 or vl in ("rachel", "adam", "antoni", "bella", "domi", "elli", "josh", "sam"):
        return "elevenlabs"
    if len(voice) == 36 and "-" in voice:
        return "cartesia"
    return None


def _detect_provider_from_tts_model(model: Optional[str]) -> Optional[str]:
    if not model or model == "default":
        return None
    ml = model.lower()
    if "sonic" in ml or "cartesia" in ml:
        return "cartesia"
    if "eleven" in ml:
        return "elevenlabs"
    if "tts-1" in ml or "openai" in ml:
        return "openai"
    if "bulbul" in ml or "sarvam" in ml:
        return "sarvam"
    if "bodhi" in ml or "navana" in ml:
        return "navana"
    if "gemini" in ml or "google" in ml:
        return "gemini"
    if "piper" in ml or "speaches" in ml:
        return "speaches"
    return None


async def _resolve_master_tts(effective: EffectiveAIModelConfiguration) -> bool:
    """Resolve sovereign TTS master credentials (Cartesia, Navana, Gemini, ElevenLabs, Sarvam, OpenAI, Deepgram, Azure)."""
    current_voice = getattr(effective.tts, "voice", None)
    configured_model = getattr(effective.tts, "model", None)
    detected_prov = _detect_provider_from_tts_model(configured_model) or _detect_provider_from_voice(current_voice)

    # 1. If voice/model belongs to a specific provider and master credentials exist, route directly
    if detected_prov and detected_prov != "speaches":
        creds = await master_credential_service.get_master_credential(detected_prov)
        if creds and creds.get("api_key"):
            default_models = {
                "cartesia": "sonic-3.5",
                "elevenlabs": "eleven_flash_v2_5",
                "openai": "tts-1",
                "gemini": "gemini-2.5-flash-preview-tts",
                "google": "gemini-2.5-flash-preview-tts",
                "sarvam": "bulbul:v1",
                "navana": "bodhi-tts-v1",
            }
            default_voices = {
                "gemini": "Puck",
                "google": "Puck",
                "openai": "alloy",
                "cartesia": "3faa81ae-d3d8-4ab1-9e44-e50e46d33c30",
                "elevenlabs": "21m00Tcm4TlvDq8ikWAM",
                "sarvam": "meera",
                "navana": "default_female",
            }
            model = configured_model if (configured_model and configured_model != "default") else default_models.get(detected_prov, "default")
            # If current voice is a Piper voice, reset to valid cloud voice
            is_local_piper_voice = current_voice and ("_IN-" in current_voice or "_US-" in current_voice or current_voice.startswith("hi_IN-"))
            target_voice = default_voices.get(detected_prov, "Puck") if is_local_piper_voice or not current_voice else current_voice
            effective.tts = _build_master_tts(detected_prov, model, creds["api_key"], target_voice)
            logger.info(f"[KodewavesResolver] Injected targeted TTS: {detected_prov}/{model}/{target_voice}")
            return True

    # 2. Fallback provider priority order
    providers_priority = [
        ("gemini", "gemini-2.5-flash-preview-tts", "Puck"),
        ("google", "gemini-2.5-flash-preview-tts", "Puck"),
        ("cartesia", "sonic-3.5", "3faa81ae-d3d8-4ab1-9e44-e50e46d33c30"),
        ("navana", "bodhi-tts-v1", "default_female"),
        ("elevenlabs", "eleven_flash_v2_5", "21m00Tcm4TlvDq8ikWAM"),
        ("sarvam", "bulbul:v1", "meera"),
        ("openai", "tts-1", "alloy"),
    ]
    for prov, default_model, fallback_voice in providers_priority:
        creds = await master_credential_service.get_master_credential(prov)
        if creds and creds.get("api_key"):
            is_local_piper_voice = current_voice and ("_IN-" in current_voice or "_US-" in current_voice or current_voice.startswith("hi_IN-"))
            voice = fallback_voice if is_local_piper_voice or not current_voice or current_voice == "default" else current_voice
            chosen_model = configured_model if (configured_model and configured_model != "default" and _detect_provider_from_tts_model(configured_model) in (None, prov)) else default_model
            effective.tts = _build_master_tts(prov, chosen_model, creds["api_key"], voice)
            logger.info(f"[KodewavesResolver] Injected master TTS: {prov}/{chosen_model}/{voice}")
            return True
    return False


async def apply_kodewaves_sovereign_resolution(
    effective: EffectiveAIModelConfiguration,
    organization_id: Optional[int] = None,
    enforce_balance: bool = False,
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
    piper_base = os.environ.get("PIPER_ENDPOINT", "http://piper:5000/synthesize").rstrip("/")
    piper_endpoint = piper_base if piper_base.endswith("/synthesize") else f"{piper_base}/synthesize"

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
            current_llm_model = getattr(effective.llm, "model", None)
            model_to_use = current_llm_model if (current_llm_model and current_llm_model != "default") else "qwen2.5:0.5b"
            effective.llm = SpeachesLLMConfiguration(
                api_key="local-cpu-token",
                model=model_to_use,
                base_url=ollama_v1_url,
            )
            is_using_local_cpu_engine = True
        elif str(provider_name).lower() in ("kodewaves", "dograh", "default") or not allow_byok or not user_key or user_key == "sovereign-managed":
            if str(provider_name).lower() in ("kodewaves", "dograh", "default"):
                resolved = await _resolve_master_llm(effective)
                if resolved:
                    is_using_master_keys = True
                else:
                    # Automatic graceful fallback to Local CPU Ollama when no cloud keys exist
                    logger.info(f"[KodewavesResolver] No cloud master LLM key configured; falling back to Local CPU Ollama for Org {organization_id}")
                    current_llm_model = getattr(effective.llm, "model", None)
                    model_to_use = current_llm_model if (current_llm_model and current_llm_model != "default") else "qwen2.5:0.5b"
                    effective.llm = SpeachesLLMConfiguration(
                        api_key="local-cpu-token",
                        model=model_to_use,
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
            current_stt_model = getattr(effective.stt, "model", None)
            stt_model_to_use = current_stt_model if (current_stt_model and current_stt_model != "default") else "Systran/faster-whisper-tiny"
            effective.stt = SpeachesSTTConfiguration(
                api_key="local-cpu-token",
                model=stt_model_to_use,
                base_url=speaches_v1_url,
            )
            is_using_local_cpu_engine = True
        elif str(provider_name).lower() in ("kodewaves", "dograh", "default") or not allow_byok or not user_key or user_key == "sovereign-managed":
            if str(provider_name).lower() in ("kodewaves", "dograh", "default"):
                resolved = await _resolve_master_stt(effective)
                if resolved:
                    is_using_master_keys = True
                else:
                    # Automatic graceful fallback to Local CPU Speaches Whisper STT
                    logger.info(f"[KodewavesResolver] No cloud master STT key configured; falling back to Local CPU Speaches STT for Org {organization_id}")
                    current_stt_model = getattr(effective.stt, "model", None)
                    stt_model_to_use = current_stt_model if (current_stt_model and current_stt_model != "default") else "Systran/faster-whisper-tiny"
                    effective.stt = SpeachesSTTConfiguration(
                        api_key="local-cpu-token",
                        model=stt_model_to_use,
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
            lang = getattr(effective.stt, "language", None) or getattr(effective.tts, "language", None) or "hi"
            default_local_voice = "hi_IN-priyamvada-medium" if str(lang).startswith("hi") else "en_US-lessac-medium"
            current_voice = getattr(effective.tts, "voice", default_local_voice)
            is_piper_voice = current_voice and ("_IN-" in current_voice or "_US-" in current_voice or "_GB-" in current_voice or "_ES-" in current_voice or "_FR-" in current_voice or "_DE-" in current_voice or "_IT-" in current_voice or current_voice.startswith(("hi_IN-", "en_US-")))
            voice = current_voice if is_piper_voice else default_local_voice
            local_tts_model = "piper"
            effective.tts = SpeachesTTSConfiguration(
                api_key="local-cpu-token",
                model=local_tts_model,
                voice=voice,
                base_url=piper_endpoint,
            )
            is_using_local_cpu_engine = True
        elif str(provider_name).lower() in ("kodewaves", "dograh", "default") or not allow_byok or not user_key or user_key == "sovereign-managed":
            if str(provider_name).lower() in ("kodewaves", "dograh", "default"):
                resolved = await _resolve_master_tts(effective)
                if resolved:
                    is_using_master_keys = True
                else:
                    # Automatic graceful fallback to Local CPU Piper ONNX TTS
                    logger.info(f"[KodewavesResolver] No cloud master TTS key configured; falling back to Local CPU Piper TTS for Org {organization_id}")
                    lang = getattr(effective.stt, "language", None) or getattr(effective.tts, "language", None) or "hi"
                    default_local_voice = "hi_IN-priyamvada-medium" if str(lang).startswith("hi") else "en_US-lessac-medium"
                    current_voice = getattr(effective.tts, "voice", default_local_voice)
                    is_piper_voice = current_voice and ("_IN-" in current_voice or "_US-" in current_voice or "_GB-" in current_voice or "_ES-" in current_voice or "_FR-" in current_voice or "_DE-" in current_voice or "_IT-" in current_voice or current_voice.startswith(("hi_IN-", "en_US-")))
                    voice = current_voice if is_piper_voice else default_local_voice
                    local_tts_model = "piper"
                    effective.tts = SpeachesTTSConfiguration(
                        api_key="local-cpu-token",
                        model=local_tts_model,
                        voice=voice,
                        base_url=piper_endpoint,
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

    # 7. Resolve Embeddings Section
    if effective.embeddings:
        emb_provider = getattr(effective.embeddings, "provider", None)
        if str(emb_provider).lower() in ("dograh", "kodewaves", "default"):
            master_creds = await master_credential_service.get_master_credential("openai")
            if master_creds and master_creds.get("api_key"):
                from api.services.configuration.registry import OpenAIEmbeddingsConfiguration
                effective.embeddings = OpenAIEmbeddingsConfiguration(
                    api_key=master_creds["api_key"],
                    model="text-embedding-3-small",
                )
            else:
                effective.embeddings = None

    # Sever external Dograh cloud proxying by clearing managed_service_version
    effective.managed_service_version = None

    # 8. Balance Enforcement for Platform-Managed Calls (only during execution)
    if enforce_balance and is_using_master_keys and not has_positive_balance:
        logger.warning(f"[KodewavesResolver] Org {organization_id} has depleted voice balance ({wallet.credit_balance_minutes} min)")
        raise HTTPException(
            status_code=402,
            detail="Your organization has zero voice credits. Please purchase a minute top-up package to continue.",
        )

    return effective
