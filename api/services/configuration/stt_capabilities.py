"""Capabilities shared by the model catalog and runtime configuration resolver."""

def stt_model_supports_auto_detect(provider: str, model: str) -> bool:
    """Return true only when the provider schema advertises auto detection.

    The import is intentionally lazy: the registry imports several provider
    modules which in turn use configuration helpers.
    """
    from api.services.configuration.registry import REGISTRY, ServiceType

    provider_key = str(provider or "").strip().casefold()
    if model == "indicconformer-ctc-int8" and provider_key in {"indicconformer", "speaches", "whisper", "local_cpu"}:
        # The serving manifest is checked separately before a call begins.
        return True
    provider_key = {
        "google_realtime": "google",
        "google_speech": "google",
        "gemini": "google",
    }.get(provider_key, provider_key)
    schema = REGISTRY.get(ServiceType.STT, {}).get(provider_key)
    if schema is None:
        return False
    language_field = schema.model_fields.get("language")
    extra = language_field.json_schema_extra if language_field else None
    if not isinstance(extra, dict):
        return False
    model_options = extra.get("model_options")
    if isinstance(model_options, dict):
        options = model_options.get(model)
        if options is None:
            return False
    else:
        options = extra.get("examples", ())
    return any(
        str(option).strip().casefold() in {"auto", "multi", "unknown"}
        for option in options
    )
