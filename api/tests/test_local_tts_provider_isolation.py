from types import SimpleNamespace


def test_local_tts_selection_does_not_use_ambient_cloud_key(monkeypatch):
    from api.services.pipecat import service_factory
    from api.services.pipecat import piper_tts

    monkeypatch.setenv("CARTESIA_API_KEY", "ambient-test-key")
    monkeypatch.setattr(service_factory.aiohttp, "ClientSession", lambda: object())
    monkeypatch.setattr(
        piper_tts,
        "PiperOwnedSessionTTSService",
        lambda **kwargs: kwargs,
    )
    user_config = SimpleNamespace(
        stt=SimpleNamespace(language="hi"),
        tts=SimpleNamespace(
            provider="kodewaves",
            model="piper",
            voice="default",
            speed=1.0,
            api_key=None,
        ),
    )

    service = service_factory.create_tts_service(
        user_config, SimpleNamespace(transport_out_sample_rate=8000)
    )

    assert service["base_url"].endswith("/synthesize")
    assert service["sample_rate"] == 8000
    assert service["settings"].voice.startswith("hi_")
