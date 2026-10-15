"""Voice compatibility declared by registered TTS models."""

from api.services.catalog.normalize import normalize_provider_name
from api.services.configuration.registry import REGISTRY, ServiceType


def model_voice_ids(provider: str, model: str | None) -> set[str] | None:
    """Return a model-specific voice pool when the provider declares one."""
    if not model or model in ("auto", "default"):
        return None
    raw_provider = (provider or "").lower().strip()
    key = "gemini" if raw_provider == "gemini" else normalize_provider_name(provider)
    if key == "google" and model.startswith("gemini"):
        key = "gemini"
    if key == "gemini" and model.startswith("gemini-3.8-"):
        # The live voice directory adds model-scoped native locale voices;
        # limiting this to the legacy named pool hides those real speakers.
        return None
    config = REGISTRY[ServiceType.TTS].get(key)
    voice = config.model_fields.get("voice") if config else None
    metadata = voice.json_schema_extra if voice else None
    if not isinstance(metadata, dict):
        return None
    pools = metadata.get("model_options") or {}
    pool = pools.get(model)
    if pool is None and key == "google":
        pool = metadata.get("examples")
    return set(pool) if pool is not None else None
