"""Capabilities shared by the model catalog and runtime configuration resolver."""


def local_stt_language_error(language: str, manifest: dict) -> str | None:
    """Reject settings that the installed recognizer cannot execute."""
    from api.services.configuration.language_normalizer import LANGUAGE_NAME_TO_ISO

    code = str(language or "").strip().casefold().replace("_", "-")
    code = LANGUAGE_NAME_TO_ISO.get(code, code).split("-", 1)[0]
    installed = {
        str(value).strip().casefold().replace("_", "-").split("-", 1)[0]
        for value in manifest.get("languages", []) if isinstance(value, str)
    }
    if code in {"auto", "multi"}:
        if manifest.get("supports_auto_detect") is not True or not installed:
            return "Installed self-hosted STT does not support automatic detection"
    elif not code or code not in installed:
        return f"Self-hosted IndicConformer does not have language '{code}' installed"
    return None

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
