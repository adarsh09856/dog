"""Capabilities shared by the model catalog and runtime configuration resolver."""


def local_stt_language_error(language: str, manifest: dict) -> str | None:
    """Reject settings that the installed recognizer cannot execute."""
    from api.services.configuration.language_normalizer import LANGUAGE_NAME_TO_ISO

    code = str(language or "").strip().casefold().replace("_", "-")
    code = LANGUAGE_NAME_TO_ISO.get(code, code).split("-", 1)[0]
    installed = {
        str(value).strip().casefold().replace("_", "-").split("-", 1)[0]
        for value in manifest.get("languages", []) if isinstance(value, str)
    }
    if code in {"auto", "multi"}:
        if manifest.get("supports_auto_detect") is not True or not installed:
            return "Installed self-hosted STT does not support automatic detection"
    elif not code or code not in installed:
        return f"Self-hosted IndicConformer does not have language '{code}' installed"
    return None

def stt_model_supports_auto_detect(provider: str, model: str) -> bool:
    """Return true only when the provider schema advertises auto detection.

    The import is intentionally lazy: the registry imports several provider
    modules which in turn use configuration helpers.
    """
    from api.services.configuration.registry import REGISTRY, ServiceType

    provider_key = str(provider or "").strip().casefold()
    if model == "indicconformer-ctc-int8" and provider_key in {"indicconformer", "speaches", "whisper", "local_cpu"}:
        # The serving manifest is checked separately before a call begins.
        return True
    provider_key = {
        "google_realtime": "google",
        "google_speech": "google",
        "gemini": "google",
    }.get(provider_key, provider_key)
    schema = REGISTRY.get(ServiceType.STT, {}).get(provider_key)
    if schema is None:
        return False
    language_field = schema.model_fields.get("language")
    extra = language_field.json_schema_extra if language_field else None
    if not isinstance(extra, dict):
        return False
    model_options = extra.get("model_options")
    if isinstance(model_options, dict):
        options = model_options.get(model)
        if options is None:
            return False
    else:
        options = extra.get("examples", ())
    return any(
        str(option).strip().casefold() in {"auto", "multi", "unknown"}
        for option in options
    )


def normalize_capability_language(language: object) -> str | None:
    if not isinstance(language, str) or not language.strip():
        return None
    code = language.strip().casefold().replace("_", "-").split("-", 1)[0]
    return None if code in {"auto", "multi", "unknown", "none", "default"} else code


def stt_model_language_codes(provider: str, model: str) -> frozenset[str]:
    """Return the selected STT model's declared language inventory."""
    from api.services.configuration.registry import REGISTRY, ServiceType

    provider_key = str(provider or "").strip().casefold()
    provider_key = {
        "google_realtime": "google", "google_speech": "google", "gemini": "google",
    }.get(provider_key, provider_key)
    schema = REGISTRY.get(ServiceType.STT, {}).get(provider_key)
    language_field = schema.model_fields.get("language") if schema is not None else None
    extra = language_field.json_schema_extra if language_field else None
    if not isinstance(extra, dict):
        return frozenset()
    model_options = extra.get("model_options")
    options = model_options.get(model) if isinstance(model_options, dict) else extra.get("examples", ())
    if not isinstance(options, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(code for item in options if (code := normalize_capability_language(item)))


def local_tts_language_codes_for_voice(
    model: str,
    voice: str,
    contract: dict[str, object] | None,
) -> frozenset[str]:
    """Return the installed local auto-router inventory for this voice/model."""
    model_key = str(model or "").strip().casefold()
    voice_key = str(voice or "").strip().casefold()
    if model_key not in {"indic-vits-rasa-13", "indic-mio-tts"} or not isinstance(contract, dict):
        return frozenset()
    if str(contract.get("model", "")).casefold() != model_key:
        return frozenset()
    voices = contract.get("voices")
    if not isinstance(voices, (set, frozenset, list, tuple)):
        return frozenset()
    installed_voices = {str(item).casefold() for item in voices}
    if voice_key not in installed_voices:
        return frozenset()
    languages = contract.get("languages")
    if not isinstance(languages, (set, frozenset, list, tuple)):
        return frozenset()
    if model_key == "indic-mio-tts":
        per_voice = contract.get("voice_languages")
        if contract.get("voice_language_metadata_present") is True or (isinstance(per_voice, dict) and per_voice):
            selected = per_voice.get(voice_key) if isinstance(per_voice, dict) else None
            if not isinstance(selected, (set, frozenset, list, tuple)):
                return frozenset()
            languages = selected
    # Rasa is an automatic router: the preferred voice is the fallback/gender
    # preference while the model's installed inventory supplies route choices.
    return frozenset(code for item in languages if (code := normalize_capability_language(item)))


def auto_language_route_error(
    *,
    stt_provider: str,
    stt_model: str,
    tts_provider: str,
    tts_model: str,
    tts_voice: str,
    local_stt_manifest: dict | None = None,
    local_tts_contract: dict[str, object] | None = None,
) -> str | None:
    """Validate that auto STT has at least one real per-turn TTS route."""
    stt_provider_key = str(stt_provider or "").strip().casefold()
    stt_model_key = str(stt_model or "").strip()
    if local_stt_manifest is not None:
        stt_error = local_stt_language_error("multi", local_stt_manifest or {})
        stt_codes = frozenset(
            code for item in (local_stt_manifest or {}).get("languages", [])
            if (code := normalize_capability_language(item))
        )
    else:
        if not stt_model_supports_auto_detect(stt_provider_key, stt_model_key):
            return f"Selected STT model '{stt_model_key}' does not support automatic language detection"
        stt_error = None
        stt_codes = stt_model_language_codes(stt_provider_key, stt_model_key)
    if stt_error:
        return stt_error

    tts_provider_key = str(tts_provider or "").strip().casefold()
    tts_model_key = str(tts_model or "").strip().casefold()
    if tts_provider_key == "sarvam" and tts_model_key == "bulbul:v3":
        from api.services.configuration.options.sarvam import (
            SARVAM_BULBUL_V3_LANGUAGE_CODES,
            SARVAM_V3_VOICES,
        )
        if str(tts_voice or "").strip().casefold() not in {voice.casefold() for voice in SARVAM_V3_VOICES}:
            return "Selected Sarvam Bulbul v3 voice is not in the verified voice inventory"
        tts_codes = frozenset(code for item in SARVAM_BULBUL_V3_LANGUAGE_CODES if (code := normalize_capability_language(item)))
    elif tts_provider_key in {"speaches", "piper", "local_cpu"}:
        tts_codes = local_tts_language_codes_for_voice(tts_model_key, tts_voice, local_tts_contract)
    else:
        tts_codes = frozenset()
    if not tts_codes:
        return "Selected TTS voice has no verified per-turn language routing; choose an explicit STT language or a verified multilingual TTS model"
    if stt_codes and not stt_codes.intersection(tts_codes):
        return "Selected STT model and TTS voice have no shared installed language for automatic routing"
    if not stt_codes:
        return "Selected STT model does not report a language inventory that can be matched to the TTS voice"
    return None
