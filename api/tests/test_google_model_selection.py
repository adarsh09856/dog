import pytest
from types import SimpleNamespace
from api.services.pipecat import service_factory as factory


@pytest.mark.parametrize("model", [
    "gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash",
    "gemini-3.8-flash-preview", "models/gemini-2.5-flash",
])
def test_explicit_google_selection_is_never_silently_replaced(model):
    assert factory._google_model_or_default(model) == model


@pytest.mark.parametrize("model", [None, "", "default", "none", " DEFAULT "])
def test_only_unspecified_google_model_uses_platform_default(model):
    assert factory._google_model_or_default(model) == "gemini-3.5-flash"


def test_google_constructor_receives_exact_selected_model(monkeypatch):
    received = {}
    def service(**kwargs):
        received.update(kwargs)
        return SimpleNamespace()
    monkeypatch.setattr(factory, "KodewavesGoogleLLMService", service)
    monkeypatch.setattr(factory, "GoogleLLMSettings", lambda **kwargs: SimpleNamespace(**kwargs))
    factory.create_llm_service_from_provider(
        "google", "gemini-2.5-flash", "synthetic-key",
    )
    assert received["settings"].model == "gemini-2.5-flash"


def test_gemini_3_8_uses_supported_low_thinking_level(monkeypatch):
    received = {}

    def service(**kwargs):
        received.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(factory, "KodewavesGoogleLLMService", service)
    monkeypatch.setattr(factory, "GoogleLLMSettings", lambda **kwargs: SimpleNamespace(**kwargs))
    factory.create_llm_service_from_provider(
        "google", "gemini-3.8-flash", "synthetic-key",
    )

    assert received["settings"].model == "gemini-3.8-flash"
    assert received["settings"].thinking == {"thinking_level": "low"}
