"""Read installed local speech capabilities from the serving engines."""

import os
import time
from typing import Any

import aiohttp

from api.utils.common import normalize_local_ai_endpoint


_tts_model_cache: dict[str, tuple[float, dict[str, dict]]] = {}
_stt_model_cache: dict[str, tuple[float, dict[str, dict]]] = {}
_TTS_MODEL_CACHE_SECONDS = 30


async def get_local_stt_models(api_base: str) -> dict[str, dict]:
    endpoint = api_base.rstrip("/")
    now = time.monotonic()
    cached = _stt_model_cache.get(endpoint)
    if cached and now - cached[0] < _TTS_MODEL_CACHE_SECONDS:
        return cached[1]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
        async with session.get(f"{endpoint}/models") as response:
            response.raise_for_status()
            payload = await response.json()
    models = {
        model["id"]: model
        for model in payload.get("data", [])
        if isinstance(model, dict)
        and isinstance(model.get("id"), str)
        and model.get("task") == "automatic-speech-recognition"
        and model.get("installed") is not False
    }
    _stt_model_cache[endpoint] = (time.monotonic(), models)
    return models


async def get_local_tts_models(api_base: str) -> dict[str, dict]:
    """Avoid a model-discovery network hop on every voice-call start.

    The cache is short-lived so an uninstalled model is rejected soon after a
    serving-engine change. Failed inventory requests are never cached.
    """
    endpoint = api_base.rstrip("/")
    cached = _tts_model_cache.get(endpoint)
    now = time.monotonic()
    if cached and now - cached[0] < _TTS_MODEL_CACHE_SECONDS:
        return cached[1]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
        async with session.get(f"{endpoint}/models") as response:
            response.raise_for_status()
            models = local_tts_inventory(await response.json())
    _tts_model_cache[endpoint] = (time.monotonic(), models)
    return models


def piper_voice_inventory(payload: Any) -> dict[str, dict]:
    """Accept Piper's voice-id mapping and compatible wrapped inventories."""
    voices = payload.get("voices", payload) if isinstance(payload, dict) else payload
    if isinstance(voices, dict):
        return {
            voice_id: metadata if isinstance(metadata, dict) else {}
            for voice_id, metadata in voices.items()
            if isinstance(voice_id, str)
            and not (isinstance(metadata, dict) and metadata.get("installed") is False)
        }
    if isinstance(voices, list):
        result = {}
        for voice in voices:
            if isinstance(voice, str):
                result[voice] = {}
            elif isinstance(voice, dict) and voice.get("installed") is not False:
                voice_id = voice.get("id") or voice.get("voice_id")
                if voice_id:
                    result[voice_id] = voice
        return result
    return {}


async def get_installed_piper_voices(endpoint: str) -> dict[str, dict]:
    base_url = endpoint.rstrip("/").removesuffix("/synthesize")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
        async with session.get(f"{base_url}/voices") as response:
            response.raise_for_status()
            return piper_voice_inventory(await response.json())


def whisper_api_base(endpoint: str) -> str:
    """Resolve the OpenAI-compatible API base, including root-only settings."""
    base = endpoint.rstrip("/").removesuffix("/models")
    return base if base.endswith("/v1") else f"{base}/v1"


def local_tts_api_base(settings: dict, model: str) -> str:
    """Use one engine choice for discovery, voice previews and live synthesis."""
    if model == "indus-pocket-tts":
        endpoint = settings.get("indus_tts_endpoint") or os.environ.get(
            "INDUS_TTS_ENDPOINT", "http://indus-tts:8000/v1"
        )
    else:
        endpoint = settings.get("whisper_endpoint") or os.environ.get(
            "WHISPER_ENDPOINT", "http://whisper:8000/v1"
        )
    return whisper_api_base(normalize_local_ai_endpoint(endpoint))


def local_tts_inventory(payload: Any) -> dict[str, dict]:
    """Use installed serving-engine capabilities, never a guessed voice pool."""
    models = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(models, list):
        return {}
    return {
        model["id"]: model
        for model in models
        if isinstance(model, dict)
        and isinstance(model.get("id"), str)
        and model.get("task") == "text-to-speech"
        and model.get("installed") is not False
    }


def local_model_voice_ids(model: dict) -> set[str]:
    voices = model.get("voices") or []
    if not isinstance(voices, (list, dict)):
        return set()
    return {
        voice if isinstance(voice, str) else voice.get("id") or voice.get("voice_id") or voice.get("name")
        for voice in voices
        if isinstance(voice, str) or (
            isinstance(voice, dict)
            and voice.get("installed") is not False
            and (voice.get("id") or voice.get("voice_id") or voice.get("name"))
        )
    }


def local_model_voice_ids_for_language(model: dict, language: str | None) -> set[str]:
    """Return voices that explicitly advertise the requested language.

    A model without per-voice language metadata keeps the legacy behavior; a
    multilingual model with metadata must not silently select a mismatched
    voice just because it is first alphabetically.
    """
    voices = model.get("voices") or []
    if not isinstance(voices, list) or not language:
        return local_model_voice_ids(model)

    if language.strip().casefold() in {"auto", "multi", "multilingual", "default"}:
        return local_model_voice_ids(model)

    requested = _language_aliases(language)
    has_language_metadata = any(
        isinstance(voice, dict) and (voice.get("languages") or voice.get("language"))
        for voice in voices
    )
    if not has_language_metadata:
        return local_model_voice_ids(model)

    result: set[str] = set()
    for voice in voices:
        if not isinstance(voice, dict) or voice.get("installed") is False:
            continue
        voice_id = voice.get("id") or voice.get("voice_id") or voice.get("name")
        languages = voice.get("languages") or voice.get("language") or []
        if isinstance(languages, str):
            languages = [languages]
        if not isinstance(languages, (list, tuple, set)):
            continue
        if voice_id and requested.intersection(
            alias for item in languages for alias in _language_aliases(str(item))
        ):
            result.add(voice_id)
    return result


def _language_aliases(language: str) -> set[str]:
    normalized = language.strip().replace("_", "-").casefold()
    base = normalized.split("-", 1)[0]
    aliases = {normalized, base}
    if base in {"hinglish", "hi-en", "en-hi"}:
        aliases.update({"hinglish", "hi", "en", "hi-in", "en-in"})
    return aliases


def local_model_voice_catalog(model: dict) -> list[dict]:
    """Expose only voices and locales actually advertised for this model."""
    rows = []
    voices = model.get("voices") or []
    if not isinstance(voices, list):
        return rows
    for voice in voices:
        metadata = voice if isinstance(voice, dict) else {}
        voice_id = voice if isinstance(voice, str) else metadata.get("id") or metadata.get("voice_id") or metadata.get("name")
        if not voice_id or metadata.get("installed") is False:
            continue
        languages = metadata.get("languages") or metadata.get("language") or []
        if isinstance(languages, str):
            languages = [languages]
        if not isinstance(languages, list):
            languages = []
        rows.append({
            "voice_id": voice_id, "name": metadata.get("name") or voice_id,
            "provider": "speaches", "gender": metadata.get("gender"),
            "accent": metadata.get("accent"), "languages": languages,
            "language": languages[0] if len(languages) == 1 else "multi",
        })
    return rows
