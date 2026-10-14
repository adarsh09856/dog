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

from api.db import db_client
from api.db.kodewaves_client import kodewaves_db_client
from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
from api.utils.common import normalize_local_ai_endpoint
from api.services.configuration.language_normalizer import (
    get_default_piper_voice_for_language,
    normalize_language_code,
    normalize_stt_language,
)
from api.services.configuration.registry import (
    REGISTRY,
    ServiceType,
    AnthropicLLMService,
    CartesiaTTSConfiguration,
    DeepgramSTTConfiguration,
    ElevenlabsTTSConfiguration,
    GoogleGeminiSTTConfiguration,
    GoogleGeminiTTSConfiguration,
    GoogleLLMService,
    GoogleTTSConfiguration,
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
    config_cls = REGISTRY.get(ServiceType.LLM, {}).get(prov_lower)
    if config_cls is None:
        raise HTTPException(status_code=400, detail=f"Unsupported platform LLM provider: {prov}")
    kwargs = {"api_key": api_key, "model": model}
    if base_url and "base_url" in config_cls.model_fields:
        kwargs["base_url"] = base_url
    return config_cls(**kwargs)


def _build_master_stt(prov: str, model: str, api_key: str, language: Optional[str] = None):
    prov_lower = prov.lower()
    norm_lang = normalize_stt_language(prov_lower, language)
    if prov_lower == "deepgram":
        return DeepgramSTTConfiguration(api_key=api_key, model=model, language=norm_lang)
    elif prov_lower == "navana":
        return NavanaSTTConfiguration(api_key=api_key, model=model, language=norm_lang)
    elif prov_lower in ("google", "gemini"):
        return GoogleGeminiSTTConfiguration(api_key=api_key, model=model, language=norm_lang)
    elif prov_lower == "sarvam":
        return SarvamSTTConfiguration(api_key=api_key, model=model, language=norm_lang)
    elif prov_lower == "groq":
        return OpenAISTTConfiguration(api_key=api_key, model=model or "whisper-large-v3", base_url="https://api.groq.com/openai/v1")
    elif prov_lower == "openai":
        return OpenAISTTConfiguration(api_key=api_key, model=model)
    config_cls = REGISTRY.get(ServiceType.STT, {}).get(prov_lower)
    if config_cls is None:
        raise HTTPException(status_code=400, detail=f"Unsupported platform STT provider: {prov}")
    return config_cls(api_key=api_key, model=model, language=norm_lang)


def _build_master_tts(prov: str, model: str, api_key: str, voice: Optional[str] = None):
    prov_lower = prov.lower()
    if prov_lower == "cartesia":
        v = voice if (voice and voice != "default") else "3faa81ae-d3d8-4ab1-9e44-e50e46d33c30"
        return CartesiaTTSConfiguration(api_key=api_key, model=model or "sonic-3.5", voice=v)
    elif prov_lower == "navana":
        v = voice if (voice and voice != "default") else "default_female"
        return NavanaTTSConfiguration(api_key=api_key, model=model or "bodhi-tts-v1", voice=v)
    elif prov_lower == "gemini":
        v = voice if (voice and voice != "default") else "Puck"
        return GoogleGeminiTTSConfiguration(api_key=api_key, model=model or "gemini-3.8-flash-lite-tts", voice=v)
    elif prov_lower == "elevenlabs":
        v = voice if (voice and voice != "default") else "21m00Tcm4TlvDq8ikWAM"
        return ElevenlabsTTSConfiguration(api_key=api_key, model=model, voice=v)
    elif prov_lower == "sarvam":
        v = voice if (voice and voice != "default") else "meera"
        return SarvamTTSConfiguration(api_key=api_key, model=model, voice=v)
    elif prov_lower == "openai":
        v = voice if (voice and voice != "default") else "alloy"
        return OpenAITTSService(api_key=api_key, model=model, voice=v)
    elif prov_lower == "google":
        return GoogleTTSConfiguration(api_key=api_key, model=model or "chirp_3_hd", voice=voice or "en-US-Chirp3-HD-Charon")
    config_cls = REGISTRY.get(ServiceType.TTS, {}).get(prov_lower)
    if config_cls is None:
        raise HTTPException(status_code=400, detail=f"Unsupported platform TTS provider: {prov}")
    kwargs = {"api_key": api_key, "model": model}
    if voice and voice != "default":
        kwargs["voice"] = voice
    return config_cls(**kwargs)


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
    if ml.startswith("groq/") or ml in ("whisper-large-v3", "whisper-large-v3-turbo") or "groq" in ml:
        return "groq"
    if ml in ("faster-whisper", "whisper-local", "systran/faster-whisper-tiny", "systran/faster-whisper-base") or "local" in ml:
        return "whisper"
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


async def _resolve_catalog_layer(effective: EffectiveAIModelConfiguration, layer: str) -> Optional[ResolvedLayerInfo]:
    """Resolve only enabled administrator catalog entries; never guess a vendor from an ID."""
    from api.services.catalog.normalize import normalize_provider_name

    current = getattr(effective, layer)
    requested = getattr(current, "model", None)
    explicit = requested not in (None, "", "auto", "default")
    models = await kodewaves_db_client.list_models(enabled_only=True)
    candidates = [m for m in models if (m.layer or m.category) == layer
                  and m.status not in ("FAIL", "UNAVAILABLE")
                  and (not explicit or m.model_identifier == requested)]
    candidates.sort(key=lambda m: (not bool(m.recommended), m.model_identifier))
    master_rows = await kodewaves_db_client.list_master_credentials()
    active = {
        (str(row.provider).lower().strip(), normalize_provider_name(row.provider))
        for row in master_rows
        if row.is_enabled and row.credentials_encrypted
    }
    for model in candidates:
        raw_provider = str(model.provider).lower().strip()
        provider = "gemini" if raw_provider == "gemini" else normalize_provider_name(model.provider)
        credential_provider = provider
        if not any(
            raw_provider == credential_provider or canonical_provider == credential_provider
            for raw_provider, canonical_provider in active
        ):
            continue
        creds = await master_credential_service.get_master_credential(credential_provider)
        if not creds or not creds.get("api_key"):
            continue
        voice = getattr(current, "voice", None)
        language = getattr(current, "language", None)
        if layer == "llm":
            config = _build_master_llm(provider, model.model_identifier, creds["api_key"], creds.get("base_url"))
        elif layer == "stt":
            config = _build_master_stt(provider, model.model_identifier, creds["api_key"], language)
        else:
            config = _build_master_tts(provider, model.model_identifier, creds["api_key"], voice)
            if current is not None and hasattr(current, "speed") and "speed" in type(config).model_fields:
                config.speed = current.speed
            spoken_language = getattr(current, "language", None) or getattr(effective.stt, "language", None)
            if spoken_language and spoken_language not in ("multi", "auto", "unknown") and "language" in type(config).model_fields:
                config.language = normalize_language_code(spoken_language, target_provider=provider)
        setattr(effective, layer, config)
        return ResolvedLayerInfo(provider=provider, model=model.model_identifier, source="master_key",
                                 voice=getattr(config, "voice", None), language=getattr(config, "language", None))
    if explicit:
        raise HTTPException(status_code=400, detail=f"Selected {layer.upper()} model '{requested}' is disabled or unavailable. Choose an available model.")
    return None


async def _resolve_master_llm(effective: EffectiveAIModelConfiguration) -> Optional[ResolvedLayerInfo]:
    return await _resolve_catalog_layer(effective, "llm")


async def _resolve_master_stt(effective: EffectiveAIModelConfiguration) -> Optional[ResolvedLayerInfo]:
    return await _resolve_catalog_layer(effective, "stt")


async def _resolve_master_tts(effective: EffectiveAIModelConfiguration) -> Optional[ResolvedLayerInfo]:
    return await _resolve_catalog_layer(effective, "tts")


async def _require_enabled_platform_model(layer: str, provider: str, model: str) -> None:
    """Recheck saved selections at execution time, including administrator revocations."""
    from api.services.catalog.normalize import normalize_provider_name

    models = await kodewaves_db_client.list_models(enabled_only=True)
    allowed_layers = {"s2s", "realtime"} if layer == "realtime" else {layer}
    if not any(
        (entry.layer or entry.category) in allowed_layers
        and entry.model_identifier == model
        and normalize_provider_name(entry.provider) == normalize_provider_name(provider)
        and entry.status not in ("FAIL", "UNAVAILABLE")
        for entry in models
    ):
        raise HTTPException(status_code=400, detail=f"Selected {layer.upper()} model '{model}' is disabled or unavailable.")


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

    # 0. Organization Status Gate
    org = await db_client.get_organization_by_id(organization_id)
    if org and getattr(org, "status", "active") in ("suspended", "churned"):
        raise HTTPException(
            status_code=403,
            detail=f"Organization access is {org.status}. Service is suspended.",
        )

    # 1. Global Policies and Wallet Check
    byok_policy = await kodewaves_db_client.get_setting("byok_policy")
    allow_byok = byok_policy.get("allow_user_byok", True) if byok_policy else True

    if not allow_byok:
        for layer in (effective.llm, effective.stt, effective.tts, effective.realtime):
            key = getattr(layer, "api_key", None)
            if key and key not in ("sovereign-managed", "default", "sovereign-local-cpu", "local-cpu-token"):
                raise HTTPException(status_code=403, detail="User-provided model keys are disabled by your administrator.")

    wallet = await kodewaves_db_client.get_or_create_wallet(organization_id)
    has_positive_balance = (wallet.credit_balance_minutes + wallet.bonus_minutes) > 0 if wallet else True

    local_engine = await kodewaves_db_client.get_setting("local_ai") or {}
    engine_enabled = local_engine.get("enable_local_ai_engine", False)
    access_policy = local_engine.get("local_ai_access_policy", "public")
    is_public_local_ai = access_policy in ("public", "all_workspaces")
    org_access = await kodewaves_db_client.get_setting(f"local_ai_org_{organization_id}")
    has_local_access = is_public_local_ai or (bool(org_access.get("enabled", False)) if org_access else False)
    org_policy = await kodewaves_db_client.get_org_ai_policy(organization_id)
    if org_policy:
        has_local_access = has_local_access and org_policy.local_allowed
        if effective.is_realtime and not org_policy.s2s_allowed:
            raise HTTPException(status_code=403, detail="Realtime models are disabled for this organization.")

    ollama_raw = local_engine.get("ollama_endpoint", "http://ollama:11434")
    ollama_base = normalize_local_ai_endpoint(ollama_raw).rstrip("/")
    ollama_v1_url = f"{ollama_base}/v1" if not ollama_base.endswith("/v1") else ollama_base

    piper_raw = local_engine.get("piper_endpoint", "http://piper:5000")
    piper_base = normalize_local_ai_endpoint(piper_raw).rstrip("/")
    piper_endpoint = f"{piper_base}/synthesize" if not piper_base.endswith("/synthesize") else piper_base

    whisper_raw = local_engine.get("whisper_endpoint", "http://whisper:8000/v1")
    whisper_base = normalize_local_ai_endpoint(whisper_raw).rstrip("/")
    whisper_v1_url = f"{whisper_base}/v1" if not whisper_base.endswith("/v1") else whisper_base

    is_using_master_keys = False


    # =========================================================================
    # 2. LLM Layer Resolution
    # =========================================================================
    if effective.llm is None:
        resolved = await _resolve_master_llm(effective)
        if resolved:
            metadata.llm = resolved
            is_using_master_keys = True
        elif engine_enabled and has_local_access:
            model_to_use = "qwen2.5:0.5b"
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
                creds = await master_credential_service.get_master_credential(provider_name)
                if creds and creds.get("api_key"):
                    await _require_enabled_platform_model("llm", provider_name, model)
                    effective.llm.api_key = creds["api_key"]
                    if creds.get("base_url") and hasattr(effective.llm, "base_url"):
                        effective.llm.base_url = creds["base_url"]
                    metadata.llm = ResolvedLayerInfo(provider=provider_name, model=model, source="master_key")
                    is_using_master_keys = True
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Requested LLM provider '{provider_name}' has no active master credentials or is disabled.",
                    )

    # =========================================================================
    # 3. STT Layer Resolution
    # =========================================================================
    if not effective.is_realtime:
        if effective.stt is None:
            resolved = await _resolve_master_stt(effective)
            if resolved:
                metadata.stt = resolved
                is_using_master_keys = True
            elif engine_enabled and has_local_access:
                model_to_use = "Systran/faster-whisper-tiny"
                effective.stt = SpeachesSTTConfiguration(
                    api_key="local-cpu-token",
                    model=model_to_use,
                    language="en",
                    base_url=whisper_v1_url,
                )
                metadata.stt = ResolvedLayerInfo(provider="whisper", model=model_to_use, source="local", language="en")
            else:
                raise HTTPException(
                    status_code=400,
                    detail="No active STT credentials configured. Please configure Deepgram, Groq, or Google in Admin Master Keys.",
                )
        else:
            provider = getattr(effective.stt, "provider", "deepgram")
            provider_name = str(getattr(provider, "value", provider)).lower()
            user_key = getattr(effective.stt, "api_key", None)
            model = getattr(effective.stt, "model", "default")
            raw_lang = getattr(effective.stt, "language", "en")
            is_local_stt = provider_name in ("whisper", "speaches", "local_cpu") or user_key in ("sovereign-local-cpu", "local-cpu-token")
            norm_lang = (
                "multi"
                if is_local_stt and str(raw_lang or "auto").lower() in ("auto", "multi", "default")
                else normalize_stt_language(provider_name, raw_lang)
            )

            if hasattr(effective.stt, "language"):
                effective.stt.language = norm_lang

            # Local Whisper STT
            if provider_name in ("whisper", "speaches", "local_cpu") or user_key in ("sovereign-local-cpu", "local-cpu-token"):
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
                            detail="No active STT credentials configured. Please configure Deepgram, Groq, or Google in Admin Master Keys.",
                        )
                else:
                    creds = await master_credential_service.get_master_credential(provider_name)
                    if creds and creds.get("api_key"):
                        await _require_enabled_platform_model("stt", provider_name, model)
                        effective.stt.api_key = creds["api_key"]
                        metadata.stt = ResolvedLayerInfo(provider=provider_name, model=model, source="master_key", language=norm_lang)
                        is_using_master_keys = True
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Requested STT provider '{provider_name}' has no active master credentials or is disabled.",
                        )

        # =========================================================================
        # 4. TTS Layer Resolution
        # =========================================================================
        if effective.tts is None:
            resolved = await _resolve_master_tts(effective)
            if resolved:
                metadata.tts = resolved
                is_using_master_keys = True
            elif engine_enabled and has_local_access:
                default_voice = get_default_piper_voice_for_language("en")
                effective.tts = SpeachesTTSConfiguration(
                    api_key="local-cpu-token",
                    model="piper",
                    voice=default_voice,
                    base_url=piper_endpoint,
                )
                metadata.tts = ResolvedLayerInfo(provider="piper", model="piper", voice=default_voice, source="local")
            else:
                raise HTTPException(
                    status_code=400,
                    detail="No active TTS credentials configured. Please configure Cartesia, Google, or ElevenLabs in Admin Master Keys.",
                )
        else:
            provider = getattr(effective.tts, "provider", "cartesia")
            provider_name = str(getattr(provider, "value", provider)).lower()
            user_key = getattr(effective.tts, "api_key", None)
            model = getattr(effective.tts, "model", "default")
            current_voice = getattr(effective.tts, "voice", None)
            stt_lang = getattr(effective.stt, "language", None) if effective.stt else None
            tts_lang = getattr(effective.tts, "language", None) or stt_lang or "en"

            # Preserve the explicitly selected local engine and voice.
            if provider_name in ("piper", "speaches", "local_cpu") or user_key in ("sovereign-local-cpu", "local-cpu-token"):
                if not engine_enabled or not has_local_access:
                    raise HTTPException(
                        status_code=403,
                        detail="Local AI Engine access is restricted or disabled. Please contact your administrator.",
                    )
                default_voice = get_default_piper_voice_for_language(tts_lang)
                voice_to_use = current_voice if current_voice and current_voice != "default" else default_voice
                selected_model = model if model not in (None, "", "default") else "piper"
                if selected_model == "speaches-ai/Kokoro-82M-v1.0-ONNX":
                    from api.services.catalog.voice_selection import model_voice_ids
                    import aiohttp

                    allowed_voices = model_voice_ids("speaches", selected_model) or set()
                    if voice_to_use not in allowed_voices:
                        raise HTTPException(status_code=400, detail="Select a voice supported by the selected local TTS model")
                    try:
                        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                            async with session.get(f"{whisper_v1_url}/models") as response:
                                inventory = await response.json() if response.status == 200 else {}
                    except (aiohttp.ClientError, TimeoutError):
                        raise HTTPException(status_code=503, detail="Local TTS model inventory is unavailable")
                    if selected_model not in {entry.get("id") for entry in inventory.get("data", [])}:
                        raise HTTPException(status_code=400, detail="Selected local TTS model is not installed")
                    local_tts_url = whisper_v1_url
                elif selected_model == "piper" or selected_model.startswith("piper/"):
                    local_tts_url = piper_endpoint
                else:
                    raise HTTPException(status_code=400, detail="Selected local TTS model is not supported")
                effective.tts = SpeachesTTSConfiguration(
                    api_key="local-cpu-token",
                    model=selected_model,
                    voice=voice_to_use,
                    speed=getattr(effective.tts, "speed", 1.0),
                    base_url=local_tts_url,
                )
                metadata.tts = ResolvedLayerInfo(provider="speaches" if selected_model != "piper" else "piper", model=selected_model, voice=voice_to_use, source="local")

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
                        voice_to_use = current_voice if current_voice and current_voice != "default" else default_voice
                        effective.tts = SpeachesTTSConfiguration(
                            api_key="local-cpu-token",
                            model="piper",
                            voice=voice_to_use,
                            speed=getattr(effective.tts, "speed", 1.0),
                            base_url=piper_endpoint,
                        )
                        metadata.tts = ResolvedLayerInfo(provider="piper", model="piper", voice=voice_to_use, source="local")
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail="No active TTS credentials configured. Please configure Cartesia, Google, or ElevenLabs in Admin Master Keys.",
                        )
                else:
                    creds = await master_credential_service.get_master_credential(provider_name)
                    if creds and creds.get("api_key"):
                        await _require_enabled_platform_model("tts", provider_name, model)
                        effective.tts.api_key = creds["api_key"]
                        metadata.tts = ResolvedLayerInfo(provider=provider_name, model=model, voice=current_voice, source="master_key")
                        is_using_master_keys = True
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Requested TTS provider '{provider_name}' has no active master credentials or is disabled.",
                        )

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
            await _require_enabled_platform_model("realtime", provider_name, model)
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
