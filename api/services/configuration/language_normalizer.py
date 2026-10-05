"""
Kodewaves Unified Language Normalizer.
Standardizes language codes and selects matching Piper/cloud voices across LLM, STT, and TTS layers.
Part 9.1 of Master Plan.
"""

from typing import Optional


LANGUAGE_NAME_TO_ISO = {
    "hindi": "hi",
    "english": "en",
    "telugu": "te",
    "tamil": "ta",
    "marathi": "mr",
    "malayalam": "ml",
    "bengali": "bn",
    "gujarati": "gu",
    "kannada": "kn",
    "punjabi": "pa",
    "odia": "or",
    "nepali": "ne",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "japanese": "ja",
    "chinese": "zh",
    "arabic": "ar",
    "russian": "ru",
    "portuguese": "pt",
    "italian": "it",
}

DEFAULT_PIPER_VOICES_BY_LANG = {
    "hi": "hi_IN-priyamvada-medium",
    "te": "te_IN-rama-medium",
    "ml": "ml_IN-ananya-medium",
    "mr": "mr_IN-rashmi-medium",
    "ta": "ta_IN-valluvar-medium",
    "bn": "bn_IN-sampa-medium",
    "ne": "ne_NP-google-medium",
    "en": "en_US-lessac-medium",
    "en-gb": "en_GB-alan-medium",
    "en-us": "en_US-lessac-medium",
}


def normalize_language_code(lang: Optional[str], target_provider: Optional[str] = None) -> str:
    """
    Normalizes arbitrary language strings ('Hindi', 'hi-IN', 'hi_in', 'en-US') to the exact format
    expected by target providers (Deepgram, Sarvam, Azure, Google, OpenAI, etc.).
    """
    if not lang or str(lang).lower().strip() in ("none", "auto", "multi", "default", ""):
        clean = "en"
    else:
        clean = str(lang).strip().lower().replace("_", "-")

    # Map full language names to ISO codes
    if clean in LANGUAGE_NAME_TO_ISO:
        iso2 = LANGUAGE_NAME_TO_ISO[clean]
    elif "-" in clean:
        iso2 = clean.split("-")[0]
    else:
        iso2 = clean

    prov = (target_provider or "").lower().strip()

    # Provider specific formatting:
    # 1. Deepgram strictly requires short 2-letter codes for standard models (e.g. 'en', 'hi', 'es')
    if prov in ("deepgram", "groq"):
        return iso2

    # 2. Sarvam and Azure expect full BCP-47 locale tags (e.g. 'hi-IN', 'en-US', 'en-IN')
    if prov in ("sarvam", "azure", "azure_speech"):
        if iso2 in ("hi", "te", "ta", "mr", "ml", "bn", "gu", "kn", "pa", "or"):
            return f"{iso2}-IN"
        if prov == "sarvam" and iso2 == "en":
            return "en-IN"
        if iso2 == "en":
            return "en-IN" if "in" in clean else "en-US"
        return f"{iso2}-{clean.split('-')[1].upper()}" if "-" in clean else f"{iso2}-US"

    # 3. Google Gemini / OpenAI
    if prov in ("google", "gemini"):
        return iso2

    return iso2


def get_default_piper_voice_for_language(lang: Optional[str]) -> str:
    """Select the best matching local Piper neural voice for a given language."""
    iso2 = normalize_language_code(lang, target_provider="piper")
    clean = str(lang or "").lower().replace("_", "-")
    if clean in ("en-gb", "british", "uk"):
        return DEFAULT_PIPER_VOICES_BY_LANG["en-gb"]
    return DEFAULT_PIPER_VOICES_BY_LANG.get(iso2, "en_US-lessac-medium")


def normalize_stt_language(provider: Optional[str], lang: Optional[str]) -> str:
    """Convenience wrapper for STT language normalization."""
    if str(lang).lower().strip() == "multi":
        return "multi"
    return normalize_language_code(lang, target_provider=provider)


def normalize_tts_language(provider: Optional[str], lang: Optional[str]) -> str:
    """Convenience wrapper for TTS language normalization."""
    return normalize_language_code(lang, target_provider=provider)


def select_piper_voice_for_language(lang: Optional[str]) -> str:
    """Alias for get_default_piper_voice_for_language."""
    return get_default_piper_voice_for_language(lang)
