"""
Canonical provider alias normalization for Kodewaves sovereign platform.
"""

def normalize_provider_name(provider: str) -> str:
    """
    Canonical provider normalization mapping all aliases to primary provider key.
    Rule:
    openai_realtime -> openai
    google_realtime -> google
    gemini -> google
    azure_realtime -> azure
    azure_speech -> azure
    bodhi -> navana
    grok_realtime -> grok
    xai -> grok
    ultravox_realtime -> ultravox
    """
    if not provider:
        return ""
    p = provider.lower().strip()
    alias_map = {
        "gemini": "google",
        "google_realtime": "google",
        "openai_realtime": "openai",
        "azure_realtime": "azure",
        "azure_speech": "azure",
        "bodhi": "navana",
        "grok_realtime": "grok",
        "xai": "grok",
        "ultravox_realtime": "ultravox",
    }
    return alias_map.get(p, p)


def tts_runtime_provider(provider: str, model: str | None) -> str:
    """Distinguish AI Studio Gemini speech from Google Cloud speech."""
    raw = str(provider).lower().strip()
    if raw == "gemini" or (
        normalize_provider_name(raw) == "google"
        and str(model or "").lower().startswith("gemini-")
    ):
        return "gemini"
    return normalize_provider_name(raw)


def google_model_layer(model: dict) -> str | None:
    """Only discover capabilities supported by our conversational adapters."""
    name = str(model.get("name", "")).removeprefix("models/").lower()
    methods = set(model.get("supportedGenerationMethods") or [])
    if not name.startswith("gemini-"):
        return None
    if any(kind in name for kind in ("image", "nano-banana", "computer-use", "robotics", "translate")):
        return None
    if "embedContent" in methods or "batchEmbedContents" in methods:
        return "embeddings"
    if "bidiGenerateContent" in methods and "transcribe" not in name:
        return "s2s"
    if "generateContent" not in methods:
        return None
    if "tts" in name:
        return "tts"
    if "transcribe" in name:
        return "stt"
    if any(kind in name for kind in ("image", "computer-use", "robotics", "embedding", "live")):
        return None
    return "llm"
