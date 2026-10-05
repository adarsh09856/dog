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
