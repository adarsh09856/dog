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
    "assamese": "as", "bodo": "brx", "dogri": "doi", "kashmiri": "ks",
    "konkani": "kok", "maithili": "mai", "manipuri": "mni", "meitei": "mni",
    "sanskrit": "sa", "santali": "sat", "sindhi": "sd", "urdu": "ur",
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
    "te": "te_IN-maya-medium",
    "ml": "ml_IN-meera-medium",
    "mr": "mr_IN-google-medium",
    "ne": "ne_NP-google-medium",
    "en": "en_US-lessac-medium",
    "en-gb": "en_GB-alan-medium",
    "en-us": "en_US-lessac-medium",
}

SPEECH_LANGUAGE_NAMES = {
    "ar": "Arabic", "bn": "Bengali", "de": "German", "en": "English",
    "es": "Spanish", "fr": "French", "gu": "Gujarati", "hi": "Hindi",
    "id": "Indonesian", "it": "Italian", "ja": "Japanese", "kn": "Kannada",
    "ko": "Korean", "ml": "Malayalam", "mr": "Marathi", "nl": "Dutch",
    "or": "Odia", "pa": "Punjabi", "pt": "Portuguese", "ru": "Russian",
    "ta": "Tamil", "te": "Telugu", "th": "Thai", "tr": "Turkish",
    "ur": "Urdu", "vi": "Vietnamese", "zh": "Chinese",
    "as": "Assamese", "brx": "Bodo", "doi": "Dogri", "ks": "Kashmiri",
    "kok": "Konkani", "mai": "Maithili", "mni": "Manipuri", "ne": "Nepali",
    "sa": "Sanskrit", "sat": "Santali", "sd": "Sindhi",
}


def _is_auto_language(value: Optional[str]) -> bool:
    return not value or str(value).strip().lower().replace("_", "-") in {
        "auto", "multi", "multilingual", "unknown", "default", "none", ""
    }


def infer_language_from_voice(provider: Optional[str], voice: Optional[str]) -> Optional[str]:
    """Infer a speech language only when a voice ID declares a locale."""
    if not voice:
        return None
    provider_key = str(provider or "").lower().strip()
    voice_key = str(voice).strip().lower().replace("-", "_")
    if provider_key in {"piper", "speaches", "local_cpu"}:
        prefix = voice_key.split("_")[0]
        if prefix in {"hf", "hm"}:
            return "hi"
        if prefix in {"af", "am"}:
            return "en"
        if len(prefix) == 2 and prefix.isalpha():
            return prefix
    # Locale-based IDs such as hi-IN-SwaraNeural and en-IN-NeerjaNeural.
    parts = voice_key.replace("_", "-").split("-")
    if len(parts) > 1 and len(parts[0]) in (2, 3) and parts[0].isalpha():
        return parts[0]
    # Navana's IDs use a language prefix without a locale.
    if provider_key == "navana" and voice_key.startswith(("hi-", "te-", "kn-", "mr-")):
        return voice_key[:2]
    return None


def resolve_agent_speech_language(user_config) -> Optional[str]:
    """Return an explicit TTS/STT language, or infer one from a locale voice."""
    if user_config is None:
        return None
    tts = getattr(user_config, "tts", None)
    stt = getattr(user_config, "stt", None)
    for service in (tts, stt):
        language = getattr(service, "language", None)
        if not _is_auto_language(language):
            return normalize_language_code(language)
    voice_language = infer_language_from_voice(
        getattr(getattr(tts, "provider", None), "value", getattr(tts, "provider", None)),
        getattr(tts, "voice", None),
    )
    return voice_language or "caller"


def speech_language_instruction(language: Optional[str]) -> Optional[str]:
    """Build a concise text-generation rule so the LLM output matches TTS."""
    if _is_auto_language(language):
        return None
    if language == "caller":
        return (
            "Final spoken-language rule (overrides earlier conflicting prompt text): "
            "reply in the same language the caller used, and use that language's "
            "normal writing system. Do not translate or transliterate into English. "
            "Keep the caller's language consistent throughout the response."
        )
    code = normalize_language_code(language)
    name = SPEECH_LANGUAGE_NAMES.get(code)
    if not name:
        return None
    if code == "hi":
        return (
            "Final spoken-language rule: understand Hindi, Hinglish (Hindi in "
            "Latin letters), English, and switches between them in one conversation. "
            "Never ask the caller to use only Hindi or repeat supplied details in "
            "another language. For speech, respond in Hindi/Hinglish using the selected "
            "Hindi voice: write Hindi words in Devanagari and preserve natural "
            "English names, product terms and numbers."
        )
    return (
        f"Final spoken-language rule (overrides earlier conflicting prompt text): "
        f"understand {name}, English, and switches between them, including "
        f"{name} written in Latin letters. Respond naturally in {name} with "
        "English terms where the caller uses them. Never require the caller to "
        "use only one language or repeat supplied details in another language. "
        "Write native-language words in their normal script for speech; preserve "
        "English names, numbers, and product terms clearly."
    )


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
    if iso2 not in DEFAULT_PIPER_VOICES_BY_LANG:
        raise ValueError(f"No Piper voice is configured for language '{iso2}'. Select an installed voice for that language.")
    return DEFAULT_PIPER_VOICES_BY_LANG[iso2]


def normalize_stt_language(provider: Optional[str], lang: Optional[str]) -> str:
    """Convenience wrapper for STT language normalization."""
    if str(lang).lower().strip() in ("multi", "auto", "unknown"):
        provider_key = str(provider or "").lower()
        if provider_key == "sarvam":
            return "unknown"
        if provider_key in ("google", "gemini"):
            return "auto"
        return "multi"
    return normalize_language_code(lang, target_provider=provider)


def normalize_tts_language(provider: Optional[str], lang: Optional[str]) -> str:
    """Convenience wrapper for TTS language normalization."""
    return normalize_language_code(lang, target_provider=provider)


def select_piper_voice_for_language(lang: Optional[str]) -> str:
    """Alias for get_default_piper_voice_for_language."""
    return get_default_piper_voice_for_language(lang)
