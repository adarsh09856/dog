from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.catalog.voice_selection import model_voice_ids
from api.services.configuration.language_normalizer import (
    resolve_agent_speech_language,
    speech_language_instruction,
)


def test_sarvam_model_pools_and_gemini_provider_alias():
    assert model_voice_ids("sarvam", "bulbul:v2") != model_voice_ids("sarvam", "bulbul:v3")
    assert "Puck" in model_voice_ids("google", "gemini-3.1-flash-tts-preview")
    assert "Journey" not in model_voice_ids("google", "gemini-3.1-flash-tts-preview")
    assert len(model_voice_ids("google", "gemini-3.1-flash-tts-preview")) == 30


def test_kokoro_local_voices_are_specific_to_the_selected_model():
    assert model_voice_ids("speaches", "speaches-ai/Kokoro-82M-v1.0-ONNX") is None
    assert resolve_agent_speech_language(SimpleNamespace(
        tts=SimpleNamespace(provider="speaches", voice="hf_alpha", language=None),
        stt=SimpleNamespace(language="multi"),
    )) == "hi"


def test_kokoro_factory_uses_speaches_endpoint_and_selected_voice(monkeypatch):
    from api.services.pipecat import service_factory

    captured = {}
    from api.services.pipecat import speaches_tts
    monkeypatch.setattr(speaches_tts, "SpeachesLiveTTSService", lambda **kwargs: captured.update(kwargs) or captured)
    user_config = SimpleNamespace(
        tts=SimpleNamespace(provider="speaches", model="speaches-ai/Kokoro-82M-v1.0-ONNX",
                            voice="hf_alpha", speed=1.0, base_url="http://whisper:8000/v1"),
        stt=SimpleNamespace(language="hi"),
    )
    result = service_factory.create_tts_service(
        user_config, SimpleNamespace(transport_out_sample_rate=8000)
    )
    assert result["base_url"] == "http://whisper:8000/v1"
    assert result["sample_rate"] == 24000
    assert result["settings"].model == "speaches-ai/Kokoro-82M-v1.0-ONNX"
    assert result["settings"].voice == "hf_alpha"


def test_local_hindi_voice_sets_the_agent_response_language_when_auto_detecting():
    config = SimpleNamespace(
        tts=SimpleNamespace(
            provider="speaches", voice="hi_IN-pratham-medium", language=None
        ),
        stt=SimpleNamespace(language="multi"),
    )

    language = resolve_agent_speech_language(config)

    assert language == "hi"
    instruction = speech_language_instruction(language)
    assert 'Hinglish' in instruction and 'English' in instruction
    assert 'Match the caller\'s language on each turn' in instruction
    assert 'Never claim that you understand or speak only Hindi' in instruction


def test_explicit_agent_language_takes_precedence_over_voice_inference():
    config = SimpleNamespace(
        tts=SimpleNamespace(
            provider="speaches", voice="hi_IN-pratham-medium", language="en"
        ),
        stt=SimpleNamespace(language="hi"),
    )

    assert resolve_agent_speech_language(config) == "en"
    assert speech_language_instruction("auto") is None


def test_multilingual_cloud_voice_follows_the_caller_language():
    config = SimpleNamespace(
        tts=SimpleNamespace(provider="google", voice="Puck", language=None),
        stt=SimpleNamespace(language="multi"),
    )

    assert resolve_agent_speech_language(config) == "caller"
    assert "same language the caller used" in speech_language_instruction("caller")


@pytest.mark.asyncio
async def test_managed_picker_limits_voices_to_selected_model_provider(monkeypatch):
    from api.routes import user as routes

    monkeypatch.setattr(routes.kodewaves_db_client, "get_setting", AsyncMock(return_value={}))
    monkeypatch.setattr(routes.kodewaves_db_client, "get_org_ai_policy", AsyncMock(return_value=None))
    monkeypatch.setattr(routes.kodewaves_db_client, "list_models", AsyncMock(return_value=[
        SimpleNamespace(layer="tts", model_identifier="bulbul:v3", provider="sarvam"),
    ]))
    monkeypatch.setattr(routes.kodewaves_db_client, "list_voices", AsyncMock(return_value=[]))
    monkeypatch.setattr(routes.master_credential_service, "get_master_credential", AsyncMock(
        side_effect=lambda provider: {"api_key": "synthetic"} if provider == "sarvam" else None))
    response = await routes.get_voices("all", model="bulbul:v3", user=SimpleNamespace(selected_organization_id=1))
    assert {voice.provider for voice in response.voices} == {"sarvam"}
    assert {voice.voice_id for voice in response.voices} == model_voice_ids("sarvam", "bulbul:v3")
    assert all("model=bulbul%3Av3" in voice.preview_url for voice in response.voices)


@pytest.mark.asyncio
async def test_unconfigured_managed_model_has_no_voice_pool(monkeypatch):
    from api.routes import user as routes

    monkeypatch.setattr(routes.kodewaves_db_client, "get_setting", AsyncMock(return_value={}))
    monkeypatch.setattr(routes.kodewaves_db_client, "get_org_ai_policy", AsyncMock(return_value=None))
    monkeypatch.setattr(routes.kodewaves_db_client, "list_models", AsyncMock(return_value=[
        SimpleNamespace(layer="tts", model_identifier="bulbul:v3", provider="sarvam"),
    ]))
    monkeypatch.setattr(routes.kodewaves_db_client, "list_voices", AsyncMock(return_value=[]))
    monkeypatch.setattr(routes.master_credential_service, "get_master_credential", AsyncMock(return_value=None))
    response = await routes.get_voices("all", model="bulbul:v3", user=SimpleNamespace(selected_organization_id=1))
    assert response.voices == []


@pytest.mark.asyncio
async def test_gemini_catalog_matches_current_model_and_reports_multilingual_support(monkeypatch):
    from api.routes import user as routes

    monkeypatch.setattr(routes.kodewaves_db_client, "get_setting", AsyncMock(return_value={}))
    monkeypatch.setattr(routes.kodewaves_db_client, "get_org_ai_policy", AsyncMock(return_value=None))
    monkeypatch.setattr(routes.kodewaves_db_client, "list_voices", AsyncMock(return_value=[]))
    monkeypatch.setattr(routes.master_credential_service, "get_master_credential", AsyncMock(
        side_effect=lambda provider: {"api_key": "synthetic"} if provider in ("google", "gemini") else None))

    response = await routes.get_voices(
        "google",
        model="gemini-3.8-flash-lite-tts",
        user=SimpleNamespace(selected_organization_id=1),
    )

    from api.services.configuration.registry import GEMINI_TTS_VOICES
    assert {voice.voice_id for voice in response.voices} == set(GEMINI_TTS_VOICES)
    assert all(voice.language == "multi" for voice in response.voices)
    assert "hi-IN" in response.facets.languages
    assert "fr-FR" in response.facets.languages

    french = await routes.get_voices(
        "google",
        model="gemini-3.8-flash-lite-tts",
        language="fr-FR",
        user=SimpleNamespace(selected_organization_id=1),
    )
    assert {voice.voice_id for voice in french.voices} == set(GEMINI_TTS_VOICES)


@pytest.mark.asyncio
async def test_preview_uses_selected_model_and_keeps_model_caches_separate(monkeypatch):
    import aiohttp
    from api.routes import user as routes

    routes._AUDIO_PREVIEW_CACHE.clear()
    monkeypatch.setattr(routes, "_resolve_tts_preview_creds", AsyncMock(return_value={"api_key": "synthetic"}))
    requests = []

    class Response:
        status = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def read(self): return b"synthetic-audio"

    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        def post(self, url, **kwargs):
            requests.append(kwargs["json"])
            return Response()

    monkeypatch.setattr(aiohttp, "ClientSession", lambda **kwargs: Session())
    actor = SimpleNamespace(selected_organization_id=99)
    for model in ("tts-1", "tts-1-hd"):
        result = await routes.preview_voice("openai", "nova", None, model=model, user=actor)
        assert result.body == b"synthetic-audio"
    assert [request["model"] for request in requests] == ["tts-1", "tts-1-hd"]
    assert all(request["voice"] == "nova" for request in requests)


@pytest.mark.asyncio
async def test_gemini_38_preview_uses_selected_language_and_current_payload(monkeypatch):
    import aiohttp
    import base64
    import json
    import io
    import wave
    from api.routes import user as routes

    routes._AUDIO_PREVIEW_CACHE.clear()
    monkeypatch.setattr(routes, "_resolve_tts_preview_creds", AsyncMock(
        return_value={"api_key": "synthetic"}))
    requests = []

    class Response:
        status = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        @property
        def content(self):
            async def events():
                for chunk in [b"\x01\x00", b"\x02\x00"]:
                    event = {"candidates": [{"content": {"parts": [{
                        "inlineData": {"mimeType": "audio/l16;rate=24000", "data": base64.b64encode(chunk).decode()}
                    }]}}]}
                    yield b"data: " + json.dumps(event).encode() + b"\n\n"
            return events()


    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        def post(self, url, **kwargs):
            requests.append((url, kwargs))
            return Response()

    monkeypatch.setattr(aiohttp, "ClientSession", lambda **kwargs: Session())
    result = await routes.preview_voice(
        "google",
        "Puck",
        None,
        model="gemini-3.8-flash-lite-tts",
        language="hi-IN",
        user=SimpleNamespace(selected_organization_id=99),
    )

    with wave.open(io.BytesIO(result.body), "rb") as audio:
        assert audio.readframes(audio.getnframes()) == b"\x01\x00\x02\x00"
    url, request = requests[0]
    assert url.endswith("/gemini-3.8-flash-lite-tts:streamGenerateContent?alt=sse")
    assert request["json"]["contents"][0]["parts"][0]["text"].startswith("नमस्ते")
    assert request["json"]["generationConfig"]["speechConfig"]["voiceConfig"] == {
        "voice": "Puck"
    }


def test_google_cloud_tts_models_do_not_advertise_gemini_ai_studio_models():
    from api.services.catalog.catalog_service import CURATED_PROVIDER_MODELS
    from api.services.configuration.options import GOOGLE_TTS_MODELS
    from api.services.configuration.registry import GEMINI_TTS_MODELS

    assert GOOGLE_TTS_MODELS == ("chirp_3_hd",)
    assert "gemini-3.8-flash-lite-tts" in GEMINI_TTS_MODELS
    assert not [model for model in CURATED_PROVIDER_MODELS["google"] if model["layer"] == "tts"]
    assert {model["model_identifier"] for model in CURATED_PROVIDER_MODELS["gemini"]} == set(GEMINI_TTS_MODELS)


def test_gemini_admin_model_resolves_to_gemini_tts_service():
    from api.services.configuration.kodewaves_resolver import _build_master_tts

    service = _build_master_tts(
        "gemini", "gemini-3.8-flash-lite-tts", "synthetic-key", "Kore"
    )

    assert service.provider == "gemini"
    assert service.model == "gemini-3.8-flash-lite-tts"
    assert service.voice == "Kore"
