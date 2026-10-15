"""Native Indian voice discovery for Gemini's newer speech models."""

import re

from api.services.configuration.registry import GEMINI_TTS_VOICES


def supports_gemini_voice(model: str, voice: str) -> bool:
    if voice in GEMINI_TTS_VOICES:
        return True
    # New library IDs are locale-qualified. The provider remains authoritative
    # for availability; reject control/path characters without silently changing
    # the selected speaker to a different voice.
    return bool(model.startswith("gemini-3.8-") and re.fullmatch(
        r"[a-z]{2,3}-[a-z]{2}-[a-z0-9][a-z0-9-]{0,100}", voice,
    ))


async def discover_indian_voices(session, api_key: str) -> list[dict]:
    """Read bounded native Hindi/Indian English pages, preserving vendor locales.

    This is an India-focused addition to the existing voice pool, not a claim
    that every catalog voice speaks every Indian language.
    """
    voices = {}
    for language in ("hi-IN", "en-IN"):
        token = None
        for _ in range(2):
            params = {"language_code": language, "region_code": "IN", "page_size": "50"}
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
                if not supports_gemini_voice("gemini-3.8-flash-tts", voice_id):
                    continue
                locale = item.get("language_code") or item.get("languageCode")
                if not locale or locale.casefold() != language.casefold():
                    continue
                name = item.get("display_name") or item.get("displayName") or voice_id
                accent = item.get("accent")
                voices[voice_id] = {
                    "voice_id": voice_id, "name": f"{name} ({accent or locale})",
                    "gender": item.get("gender"), "languages": [locale],
                }
            next_token = body.get("next_page_token") or body.get("nextPageToken")
            if not next_token or next_token == token:
                break
            token = next_token
    return list(voices.values())
