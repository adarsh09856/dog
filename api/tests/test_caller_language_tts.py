from types import SimpleNamespace

import pytest

from api.services.configuration.registry import ServiceProviders
from api.services.pipecat.caller_language_tts import CallerLanguageSarvamTTSMixin
from api.services.pipecat.service_factory import create_tts_service


class _Settings:
    def __init__(self, **values):
        self.__dict__.update(values)


class _FakeSarvamTTSService:
    Settings = _Settings

    def __init__(self, *, settings, **kwargs):
        self._settings = settings
        self._config = SimpleNamespace(speakers=(settings.voice,))
        self.kwargs = kwargs

    async def _update_settings(self, settings):
        # Pipecat updates the connection language without changing its voice.
        self._settings.language = settings.language


@pytest.mark.asyncio
async def test_sarvam_factory_routes_explicit_language_and_keeps_configured_voice(monkeypatch):
    import api.services.pipecat.service_factory as factory

    monkeypatch.setattr(factory, "SarvamTTSService", _FakeSarvamTTSService)
    monkeypatch.setattr(factory, "SarvamTTSSettings", _Settings)
    user_config = SimpleNamespace(tts=SimpleNamespace(
        provider=ServiceProviders.SARVAM.value,
        api_key="test-key",
        model="bulbul:v3",
        voice="anushka",
        language="hi-IN",
        speed=1.0,
    ))

    tts = create_tts_service(user_config, SimpleNamespace())

    assert isinstance(tts, CallerLanguageSarvamTTSMixin)
    assert tts._settings.language.value in {"hi-IN", "hi"}
    assert tts._settings.voice == "anushka"
    tts._caller_language_source = SimpleNamespace(
        reply_language_override="en",
        latest_tts_language="hi",
    )

    await tts._apply_caller_language()

    assert tts._settings.language.value in {"en-IN", "en"}
    assert tts._settings.voice == "anushka"


def test_sarvam_language_resolver_prefers_explicit_override_over_stt():
    from api.services.pipecat.caller_language_tts import caller_reply_language

    source = SimpleNamespace(reply_language_override="en", latest_tts_language="hi")

    assert caller_reply_language(source, configured_language="hi") == "en"
