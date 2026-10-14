"""Voice compatibility declared by registered TTS models."""

from api.services.catalog.normalize import normalize_provider_name
from api.services.configuration.registry import REGISTRY, ServiceType


def model_voice_ids(provider: str, model: str | None) -> set[str] | None:
    """Return a model-specific voice pool when the provider declares one."""
    if not model or model in ("auto", "default"):
        return None
    key = normalize_provider_name(provider)
    if key == "google" and model.startswith("gemini"):
        key = "gemini"
    config = REGISTRY[ServiceType.TTS].get(key)
    voice = config.model_fields.get("voice") if config else None
    metadata = voice.json_schema_extra if voice else None
    if not isinstance(metadata, dict):
        return None
    pools = metadata.get("model_options") or {}
    pool = pools.get(model)
    if pool is None and normalize_provider_name(provider) == "google":
        pool = metadata.get("examples")
    return set(pool) if pool is not None else None
