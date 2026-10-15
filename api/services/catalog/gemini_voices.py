"""Native Indian voice discovery for Gemini's newer speech models."""

import re
from loguru import logger

from api.services.configuration.registry import GEMINI_TTS_VOICES


def supports_gemini_voice(model: str, voice: str) -> bool:
    if voice in GEMINI_TTS_VOICES:
        return True
    # New library IDs are locale-qualified. The provider remains authoritative
    # for availability; reject control/path characters without silently changing
    # the selected speaker to a different voice.
    return bool(model.startswith("gemini-3.8-") and re.fullmatch(
        r"[a-z]{2,3}-(?:[a-z]{4}-)?[a-z]{2}-[a-z0-9][a-z0-9-]{0,100}", voice,
    ))


async def discover_indian_voices(session, api_key: str) -> list[dict]:
    """Read the India-region directory across languages, preserving vendor locales."""
    voices = {}
    token = None
    seen_tokens = set()
    for _ in range(20):
        params = {"region_code": "IN", "page_size": "100"}
        if token:
            params["page_token"] = token
        async with session.get(
            "https://generativelanguage.googleapis.com/v1beta/voices",
            params=params, headers={"x-goog-api-key": api_key},
        ) as response:
            if response.status != 200:
                raise RuntimeError(f"Gemini voice discovery failed (HTTP {response.status})")
            body = await response.json()
        for item in body.get("voices", []):
            voice_id = item.get("id") or ""
            if len(voice_id) > 100 or not supports_gemini_voice("gemini-3.8-flash-tts", voice_id):
                continue
            locale = item.get("language_code") or item.get("languageCode")
            if not locale or not (locale.lower().endswith("-in") or locale.lower() == "ne-np"):
                continue
            name = item.get("display_name") or item.get("displayName") or voice_id
            accent = item.get("accent")
            voices[voice_id] = {
                "voice_id": voice_id, "name": f"{name} ({accent or locale})"[:100],
                "gender": item.get("gender"), "languages": [locale],
            }
        next_token = body.get("next_page_token") or body.get("nextPageToken")
        if not next_token or next_token in seen_tokens:
            break
        seen_tokens.add(next_token)
        token = next_token
    else:
        logger.warning("Gemini India voice discovery reached its 20-page safety limit; directory may be partial")
    return list(voices.values())
