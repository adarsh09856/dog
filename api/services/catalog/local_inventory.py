"""Read installed local speech capabilities from the serving engines."""

from typing import Any

import aiohttp


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
