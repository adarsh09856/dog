"""
Kodewaves Sovereign Resolver.
Unifies credential resolution, typed source attribution ('user_key' | 'master_key' | 'local'),
language normalization, and zero-silent-fallback invariants.
Part 2.1 Step 8, Part 3.2, and Work Package 4 of Master Plan.
"""

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Literal, Optional

from fastapi import HTTPException
from loguru import logger

from api.db.kodewaves_client import kodewaves_db_client
from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
from api.services.configuration.language_normalizer import (
    get_default_piper_voice_for_language,
    normalize_language_code,
)
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
    SpeachesSTTConfiguration,
    SpeachesTTSConfiguration,
)
from api.services.credentials.master_credential_service import master_credential_service

CredentialSource = Literal["user_key", "master_key", "local"]


@dataclass
class ResolvedLayerInfo:
    provider: str
    model: str
    source: CredentialSource
    voice: Optional[str] = None
    language: Optional[str] = None


@dataclass
class ResolutionMetadata:
    llm: Optional[ResolvedLayerInfo] = None
    stt: Optional[ResolvedLayerInfo] = None
    tts: Optional[ResolvedLayerInfo] = None
    realtime: Optional[ResolvedLayerInfo] = None
    overall_source: CredentialSource = "master_key"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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


def _build_master_stt(prov: str, model: str, api_key: str, language: Optional[str] = None):
    prov_lower = prov.lower()
    norm_lang = normalize_language_code(language, target_provider=prov_lower)
    if prov_lower == "deepgram":
        return DeepgramSTTConfiguration(api_key=api_key, model=model, language=norm_lang)
    elif prov_lower == "navana":
        return NavanaSTTConfiguration(api_key=api_key, model=model)
    elif prov_lower in ("google", "gemini"):
        return GoogleGeminiSTTConfiguration(api_key=api_key, model=model)
    elif prov_lower == "sarvam":
        return SarvamSTTConfiguration(api_key=api_key, model=model)
    elif prov_lower == "openai":
        return OpenAISTTConfiguration(api_key=api_key, model=model)
    return DeepgramSTTConfiguration(api_key=api_key, model=model, language=norm_lang)


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
        return GoogleGeminiTTSConfiguration(api_key=api_key, model=model or "gemini-3.1-flash-tts-preview", voice=v)
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
        return "google"
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
    if "gemini" in ml or "google" in ml:
        return "google"
    if "azure" in ml:
        return "azure"
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
        return "google"
    if "piper" in ml or "speaches" in ml:
        return "piper"
    return None


async def _resolve_master_llm(effective: EffectiveAIModelConfiguration) -> Optional[ResolvedLayerInfo]:
    """Resolve sovereign LLM master credentials in priority order when not specified."""
    current_model = getattr(effective.llm, "model", None)
    detected_prov = _detect_provider_from_llm_model(current_model)

    if detected_prov:
        creds = await master_credential_service.get_master_credential(detected_prov)
        if creds and creds.get("api_key"):
            effective.llm = _build_master_llm(detected_prov, current_model, creds["api_key"], creds.get("base_url"))
            return ResolvedLayerInfo(provider=detected_prov, model=current_model, source="master_key")

    providers_priority = [
        ("google", "gemini-3.5-flash"),
        ("openai", "gpt-4o-mini"),
        ("anthropic", "claude-haiku-4-5-20251001"),
        ("sarvam", "sarvam-105b"),
        ("groq", "llama-3.3-70b-versatile"),
    ]
    for prov, default_model in providers_priority:
        creds = await master_credential_service.get_master_credential(prov)
        if creds and creds.get("api_key"):
            model = current_model if (current_model and current_model != "default" and _detect_provider_from_llm_model(current_model) in (None, prov)) else default_model
            effective.llm = _build_master_llm(prov, model, creds["api_key"], creds.get("base_url"))
            return ResolvedLayerInfo(provider=prov, model=model, source="master_key")
    return None


async def _resolve_master_stt(effective: EffectiveAIModelConfiguration) -> Optional[ResolvedLayerInfo]:
    """Resolve sovereign STT master credentials in priority order when not specified."""
    current_model = getattr(effective.stt, "model", None)
    current_lang = getattr(effective.stt, "language", None)
    detected_prov = _detect_provider_from_stt_model(current_model)

    if detected_prov:
        creds = await master_credential_service.get_master_credential(detected_prov)
        if creds and creds.get("api_key"):
            effective.stt = _build_master_stt(detected_prov, current_model, creds["api_key"], current_lang)
            return ResolvedLayerInfo(provider=detected_prov, model=current_model, source="master_key", language=current_lang)

    providers_priority = [
        ("deepgram", "nova-3"),
        ("google", "gemini-3.5-flash"),
        ("navana", "hi-banking-v2-8khz"),
        ("sarvam", "saarika:v2.5"),
        ("openai", "whisper-1"),
    ]
    for prov, default_model in providers_priority:
        creds = await master_credential_service.get_master_credential(prov)
        if creds and creds.get("api_key"):
            model = current_model if (current_model and current_model != "default" and _detect_provider_from_stt_model(current_model) in (None, prov)) else default_model
            effective.stt = _build_master_stt(prov, model, creds["api_key"], current_lang)
            return ResolvedLayerInfo(provider=prov, model=model, source="master_key", language=current_lang)
    return None


async def _resolve_master_tts(effective: EffectiveAIModelConfiguration) -> Optional[ResolvedLayerInfo]:
    """Resolve sovereign TTS master credentials in priority order when not specified."""
    current_voice = getattr(effective.tts, "voice", None)
    configured_model = getattr(effective.tts, "model", None)
    detected_prov = _detect_provider_from_tts_model(configured_model)

    default_models = {
        "cartesia": "sonic-3.5",
        "elevenlabs": "eleven_flash_v2_5",
        "openai": "tts-1",
        "google": "gemini-3.1-flash-tts-preview",
        "sarvam": "bulbul:v2",
        "navana": "bodhi-tts-v1",
    }
    default_voices = {
        "google": "Puck",
        "openai": "alloy",
        "cartesia": "3faa81ae-d3d8-4ab1-9e44-e50e46d33c30",
        "elevenlabs": "21m00Tcm4TlvDq8ikWAM",
        "sarvam": "meera",
        "navana": "default_female",
    }

    if detected_prov and detected_prov != "piper":
        creds = await master_credential_service.get_master_credential(detected_prov)
        if creds and creds.get("api_key"):
            model = configured_model if (configured_model and configured_model != "default") else default_models.get(detected_prov, "default")
            is_local_piper_voice = current_voice and ("_IN-" in current_voice or "_US-" in current_voice)
            target_voice = default_voices.get(detected_prov, "Puck") if is_local_piper_voice or not current_voice else current_voice
            effective.tts = _build_master_tts(detected_prov, model, creds["api_key"], target_voice)
            return ResolvedLayerInfo(provider=detected_prov, model=model, voice=target_voice, source="master_key")

    providers_priority = [
        ("google", "gemini-3.1-flash-tts-preview", "Puck"),
        ("cartesia", "sonic-3.5", "3faa81ae-d3d8-4ab1-9e44-e50e46d33c30"),
        ("navana", "bodhi-tts-v1", "default_female"),
        ("elevenlabs", "eleven_flash_v2_5", "21m00Tcm4TlvDq8ikWAM"),
        ("sarvam", "bulbul:v2", "meera"),
        ("openai", "tts-1", "alloy"),
    ]
    for prov, default_model, fallback_voice in providers_priority:
        creds = await master_credential_service.get_master_credential(prov)
        if creds and creds.get("api_key"):
            is_local_piper_voice = current_voice and ("_IN-" in current_voice or "_US-" in current_voice)
            voice = fallback_voice if is_local_piper_voice or not current_voice or current_voice == "default" else current_voice
            chosen_model = configured_model if (configured_model and configured_model != "default") else default_model
            effective.tts = _build_master_tts(prov, chosen_model, creds["api_key"], voice)
            return ResolvedLayerInfo(provider=prov, model=chosen_model, voice=voice, source="master_key")
    return None


async def apply_kodewaves_sovereign_resolution(
    effective: EffectiveAIModelConfiguration,
    organization_id: Optional[int] = None,
    enforce_balance: bool = False,
) -> EffectiveAIModelConfiguration:
    """
    Sovereign credential and capability resolver.
    - Resolves BYOK, Platform Master Keys, or Local Engine per layer.
    - Enforces ZERO silent fallback: missing credentials on explicit providers raise 400.
    - Normalizes language codes.
    - Enforces wallet minute balances for platform master key usage.
    - Sets typed resolution metadata onto effective.resolution_info.
    """
    metadata = ResolutionMetadata()

    if organization_id is None:
        effective.resolution_info = metadata.to_dict()
        return effective

    # 1. Global Policies and Wallet Check
    byok_policy = await kodewaves_db_client.get_setting("byok_policy")
    allow_byok = byok_policy.get("allow_user_byok", True) if byok_policy else True

    wallet = await kodewaves_db_client.get_or_create_wallet(organization_id)
    has_positive_balance = (wallet.credit_balance_minutes + wallet.bonus_minutes) > 0 if wallet else True

    local_engine = await kodewaves_db_client.get_setting("local_ai") or {}
    engine_enabled = local_engine.get("enable_local_ai_engine", False)
    access_policy = local_engine.get("local_ai_access_policy", "public")
    is_public_local_ai = access_policy in ("public", "all_workspaces")
    org_access = await kodewaves_db_client.get_setting(f"local_ai_org_{organization_id}")
    has_local_access = is_public_local_ai or (bool(org_access.get("enabled", False)) if org_access else False)

    ollama_base = local_engine.get("ollama_endpoint", "http://ollama:11434").rstrip("/")
    ollama_v1_url = f"{ollama_base}/v1" if not ollama_base.endswith("/v1") else ollama_base
    piper_base = local_engine.get("piper_endpoint", "http://piper:5000").rstrip("/")
    piper_endpoint = f"{piper_base}/synthesize" if not piper_base.endswith("/synthesize") else piper_base
    whisper_base = local_engine.get("whisper_endpoint", "http://whisper:8000/v1").rstrip("/")
    whisper_v1_url = f"{whisper_base}/v1" if not whisper_base.endswith("/v1") else whisper_base

    is_using_master_keys = False

    # =========================================================================
    # 2. LLM Layer Resolution
    # =========================================================================
    if effective.llm:
        provider = getattr(effective.llm, "provider", "openai")
        provider_name = str(getattr(provider, "value", provider)).lower()
        user_key = getattr(effective.llm, "api_key", None)
        model = getattr(effective.llm, "model", "default")

        # Local Ollama
        if provider_name in ("ollama", "speaches") or user_key == "sovereign-local-cpu":
            if not engine_enabled or not has_local_access:
                raise HTTPException(
                    status_code=403,
                    detail="Local AI Engine access is restricted or disabled. Please contact your administrator.",
                )
            model_to_use = model if model and model != "default" else "qwen2.5:0.5b"
            effective.llm = OpenAILLMService(
                api_key="sovereign-local-cpu",
                model=model_to_use,
                base_url=ollama_v1_url,
            )
            metadata.llm = ResolvedLayerInfo(provider="ollama", model=model_to_use, source="local")

        # BYOK User Key
        elif user_key and user_key not in ("sovereign-managed", "default") and allow_byok:
            metadata.llm = ResolvedLayerInfo(provider=provider_name, model=model, source="user_key")

        # Platform Master Key or Default
        else:
            if provider_name in ("kodewaves", "dograh", "default"):
                resolved = await _resolve_master_llm(effective)
                if resolved:
                    metadata.llm = resolved
                    is_using_master_keys = True
                elif engine_enabled and has_local_access:
                    model_to_use = model if model and model != "default" else "qwen2.5:0.5b"
                    effective.llm = OpenAILLMService(
                        api_key="sovereign-local-cpu",
                        model=model_to_use,
                        base_url=ollama_v1_url,
                    )
                    metadata.llm = ResolvedLayerInfo(provider="ollama", model=model_to_use, source="local")
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="No active LLM credentials configured. Please configure an API key in Admin Master Keys.",
                    )
            else:
                # Explicit provider requested -> Zero silent fallback!
                creds = await master_credential_service.get_master_credential(provider_name)
                if not creds or not creds.get("api_key"):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Requested LLM provider '{provider_name}' has no active master credentials or is disabled.",
                    )
                effective.llm.api_key = creds["api_key"]
                if creds.get("base_url") and hasattr(effective.llm, "base_url"):
                    effective.llm.base_url = creds["base_url"]
                metadata.llm = ResolvedLayerInfo(provider=provider_name, model=model, source="master_key")
                is_using_master_keys = True

    # =========================================================================
    # 3. STT Layer Resolution
    # =========================================================================
    if effective.stt:
        provider = getattr(effective.stt, "provider", "deepgram")
        provider_name = str(getattr(provider, "value", provider)).lower()
        user_key = getattr(effective.stt, "api_key", None)
        model = getattr(effective.stt, "model", "default")
        raw_lang = getattr(effective.stt, "language", "en")
        norm_lang = normalize_language_code(raw_lang, target_provider=provider_name)

        if hasattr(effective.stt, "language"):
            effective.stt.language = norm_lang

        # Local Whisper STT
        if provider_name in ("whisper", "speaches", "local_cpu") or user_key == "sovereign-local-cpu":
            if not engine_enabled or not has_local_access:
                raise HTTPException(
                    status_code=403,
                    detail="Local AI Engine access is restricted or disabled. Please contact your administrator.",
                )
            model_to_use = model if model and model != "default" else "Systran/faster-whisper-tiny"
            effective.stt = SpeachesSTTConfiguration(
                api_key="local-cpu-token",
                model=model_to_use,
                language=norm_lang,
                base_url=whisper_v1_url,
            )
            metadata.stt = ResolvedLayerInfo(provider="whisper", model=model_to_use, source="local", language=norm_lang)

        # BYOK User Key
        elif user_key and user_key not in ("sovereign-managed", "default") and allow_byok:
            metadata.stt = ResolvedLayerInfo(provider=provider_name, model=model, source="user_key", language=norm_lang)

        # Platform Master Key or Default
        else:
            if provider_name in ("kodewaves", "dograh", "default"):
                resolved = await _resolve_master_stt(effective)
                if resolved:
                    metadata.stt = resolved
                    is_using_master_keys = True
                elif engine_enabled and has_local_access:
                    model_to_use = model if model and model != "default" else "Systran/faster-whisper-tiny"
                    effective.stt = SpeachesSTTConfiguration(
                        api_key="local-cpu-token",
                        model=model_to_use,
                        language=norm_lang,
                        base_url=whisper_v1_url,
                    )
                    metadata.stt = ResolvedLayerInfo(provider="whisper", model=model_to_use, source="local", language=norm_lang)
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="No active STT credentials configured. Please configure Deepgram or Google API key in Admin Master Keys.",
                    )
            else:
                # Explicit provider requested -> Zero silent fallback!
                creds = await master_credential_service.get_master_credential(provider_name)
                if not creds or not creds.get("api_key"):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Requested STT provider '{provider_name}' has no active master credentials or is disabled.",
                    )
                effective.stt.api_key = creds["api_key"]
                metadata.stt = ResolvedLayerInfo(provider=provider_name, model=model, source="master_key", language=norm_lang)
                is_using_master_keys = True

    # =========================================================================
    # 4. TTS Layer Resolution
    # =========================================================================
    if effective.tts:
        provider = getattr(effective.tts, "provider", "cartesia")
        provider_name = str(getattr(provider, "value", provider)).lower()
        user_key = getattr(effective.tts, "api_key", None)
        model = getattr(effective.tts, "model", "default")
        current_voice = getattr(effective.tts, "voice", None)
        stt_lang = getattr(effective.stt, "language", None) if effective.stt else None
        tts_lang = getattr(effective.tts, "language", None) or stt_lang or "en"

        # Local Piper TTS
        if provider_name in ("piper", "speaches", "local_cpu") or user_key == "sovereign-local-cpu":
            if not engine_enabled or not has_local_access:
                raise HTTPException(
                    status_code=403,
                    detail="Local AI Engine access is restricted or disabled. Please contact your administrator.",
                )
            default_voice = get_default_piper_voice_for_language(tts_lang)
            voice_to_use = current_voice if current_voice and current_voice not in ("default", "none", "Puck", "alloy") else default_voice
            effective.tts = SpeachesTTSConfiguration(
                api_key="local-cpu-token",
                model="piper",
                voice=voice_to_use,
                base_url=piper_endpoint,
            )
            metadata.tts = ResolvedLayerInfo(provider="piper", model="piper", voice=voice_to_use, source="local")

        # BYOK User Key
        elif user_key and user_key not in ("sovereign-managed", "default") and allow_byok:
            metadata.tts = ResolvedLayerInfo(provider=provider_name, model=model, voice=current_voice, source="user_key")

        # Platform Master Key or Default
        else:
            if provider_name in ("kodewaves", "dograh", "default"):
                resolved = await _resolve_master_tts(effective)
                if resolved:
                    metadata.tts = resolved
                    is_using_master_keys = True
                elif engine_enabled and has_local_access:
                    default_voice = get_default_piper_voice_for_language(tts_lang)
                    voice_to_use = current_voice if current_voice and current_voice not in ("default", "none", "Puck", "alloy") else default_voice
                    effective.tts = SpeachesTTSConfiguration(
                        api_key="local-cpu-token",
                        model="piper",
                        voice=voice_to_use,
                        base_url=piper_endpoint,
                    )
                    metadata.tts = ResolvedLayerInfo(provider="piper", model="piper", voice=voice_to_use, source="local")
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="No active TTS credentials configured. Please configure Cartesia, Google, or ElevenLabs in Admin Master Keys.",
                    )
            else:
                # Explicit provider requested -> Zero silent fallback!
                creds = await master_credential_service.get_master_credential(provider_name)
                if not creds or not creds.get("api_key"):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Requested TTS provider '{provider_name}' has no active master credentials or is disabled.",
                    )
                effective.tts.api_key = creds["api_key"]
                metadata.tts = ResolvedLayerInfo(provider=provider_name, model=model, voice=current_voice, source="master_key")
                is_using_master_keys = True

    # =========================================================================
    # 5. S2S / Realtime Resolution
    # =========================================================================
    if effective.is_realtime and effective.realtime:
        provider = getattr(effective.realtime, "provider", "openai")
        provider_name = str(getattr(provider, "value", provider)).lower()
        user_key = getattr(effective.realtime, "api_key", None)
        model = getattr(effective.realtime, "model", "default")

        if user_key and user_key not in ("sovereign-managed", "default") and allow_byok:
            metadata.realtime = ResolvedLayerInfo(provider=provider_name, model=model, source="user_key")
        else:
            creds = await master_credential_service.get_master_credential(provider_name)
            if not creds or not creds.get("api_key"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Requested S2S Realtime provider '{provider_name}' has no active master credentials or is disabled.",
                )
            effective.realtime.api_key = creds["api_key"]
            metadata.realtime = ResolvedLayerInfo(provider=provider_name, model=model, source="master_key")
            is_using_master_keys = True

    # =========================================================================
    # 6. Overall Source and Balance Enforcement
    # =========================================================================
    sources = set()
    for layer in (metadata.llm, metadata.stt, metadata.tts, metadata.realtime):
        if layer:
            sources.add(layer.source)

    if "master_key" in sources:
        metadata.overall_source = "master_key"
    elif "local" in sources and len(sources) == 1:
        metadata.overall_source = "local"
    else:
        metadata.overall_source = "user_key"

    # Sever legacy external proxying
    effective.managed_service_version = None
    effective.resolution_info = metadata.to_dict()

    if enforce_balance and is_using_master_keys and not has_positive_balance:
        logger.warning(f"[KodewavesResolver] Org {organization_id} voice minutes depleted.")
        raise HTTPException(
            status_code=402,
            detail="Your organization has zero voice credits. Please purchase a minute top-up package to continue.",
        )

    return effective
