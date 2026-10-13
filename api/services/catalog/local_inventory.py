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
