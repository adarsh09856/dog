from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.routes import user as routes


@pytest.mark.parametrize("model,setting,env_name,default", [
    ("indus-pocket-tts", "indus_tts_endpoint", "INDUS_TTS_ENDPOINT", "http://indus-tts:8000/v1"),
    ("indic-mio-tts", "indic_mio_tts_endpoint", "INDIC_MIO_TTS_ENDPOINT", "http://indic-mio-tts:8000/v1"),
    ("indic-parler-tts", "indic_parler_tts_endpoint", "INDIC_PARLER_TTS_ENDPOINT", "http://indic-parler-tts:8000/v1"),
    ("indic-vits-rasa-13", "indic_vits_tts_endpoint", "INDIC_VITS_TTS_ENDPOINT", "http://indic-vits-tts:8000/v1"),
    ("dhvaani-0.5", "dhvaani_tts_endpoint", "DHVAANI_TTS_ENDPOINT", "http://dhvaani-tts:8000/v1"),
    ("speaches-ai/Kokoro-82M-v1.0-ONNX", "whisper_endpoint", "WHISPER_ENDPOINT", "http://whisper:8000/v1"),
])
def test_local_tts_endpoint_uses_admin_setting_then_environment(monkeypatch, model, setting, env_name, default):
    import socket
    from api.services.catalog.local_inventory import local_tts_api_base

    monkeypatch.setattr(socket, "gethostbyname", lambda _host: "127.0.0.1")
    monkeypatch.delenv(env_name, raising=False)
    assert local_tts_api_base({}, model) == default
    monkeypatch.setenv(env_name, "http://environment-speech:9000")
    assert local_tts_api_base({}, model) == "http://environment-speech:9000/v1"
    assert local_tts_api_base({setting: ""}, model) == "http://environment-speech:9000/v1"
    assert local_tts_api_base({setting: "http://configured-speech:9001/v1/models"}, model) == "http://configured-speech:9001/v1"


@pytest.mark.asyncio
@pytest.mark.parametrize("model,voice,setting", [
    ("indus-pocket-tts", "Inaya", "indus_tts_endpoint"),
    ("indic-mio-tts", "default", "indic_mio_tts_endpoint"),
    ("indic-parler-tts", "Divya", "indic_parler_tts_endpoint"),
    ("indic-vits-rasa-13", "MAR_F", "indic_vits_tts_endpoint"),
    ("dhvaani-0.5", "evaluation-female", "dhvaani_tts_endpoint"),
    ("speaches-ai/Kokoro-82M-v1.0-ONNX", "hf_beta", "whisper_endpoint"),
])
async def test_selected_local_model_voice_picker_and_preview_use_same_engine(monkeypatch, model, voice, setting):
    import aiohttp
    from api.services.catalog.catalog_service import catalog_service

    settings = {"enable_local_ai_engine": True, setting: "http://selected-engine:9001/v1"}
    monkeypatch.setattr(routes.kodewaves_db_client, "get_setting", AsyncMock(return_value=settings))
    monkeypatch.setattr(routes.kodewaves_db_client, "get_org_ai_policy", AsyncMock(return_value=None))
    monkeypatch.setattr(routes.kodewaves_db_client, "list_voices", AsyncMock(return_value=[]))
    monkeypatch.setattr(routes.master_credential_service, "get_master_credential", AsyncMock(return_value=None))
    monkeypatch.setattr(catalog_service, "get_available_catalog", AsyncMock(return_value={"local_engine_enabled": True}))
    routes._AUDIO_PREVIEW_CACHE.clear()
    requests = []
    inventory = {"data": [{"id": model, "task": "text-to-speech", "installed": True, "voices": [{
        "id": voice, "gender": "female", "languages": ["hi-IN", "en-IN"],
        "preview_text": "नमस्ते। Hello.",
    }]}]}

    class Response:
        status = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        async def json(self): return inventory
        async def read(self): return b"selected-model-audio"

    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        def get(self, url):
            requests.append(("GET", url, None))
            return Response()
        def post(self, url, **kwargs):
            requests.append(("POST", url, kwargs["json"]))
            return Response()

    monkeypatch.setattr(aiohttp, "ClientSession", lambda **_kwargs: Session())
    user = SimpleNamespace(selected_organization_id=57, has_local_ai_access=True)
    voices = await routes.get_voices("speaches", model=model, user=user)
    assert [item.voice_id for item in voices.voices] == [voice]
    assert voices.facets.languages == ["en-IN", "hi-IN"]
    assert "model=" in voices.voices[0].preview_url
    preview = await routes.preview_voice("speaches", voice, None, model=model, user=user)
    assert preview.body == b"selected-model-audio"
    assert all(url.startswith("http://selected-engine:9001/v1/") for _, url, _ in requests)
    assert requests[-1] == ("POST", "http://selected-engine:9001/v1/audio/speech", {
        "model": model, "voice": voice, "input": "नमस्ते। Hello.", "response_format": "wav",
    })

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        await routes.preview_voice("speaches", "uninstalled-voice", None, model=model, user=user)
    assert error.value.status_code == 400
    assert len([item for item in requests if item[0] == "POST"]) == 1


@pytest.mark.asyncio
async def test_voice_picker_only_offers_installed_local_voices(monkeypatch):
    monkeypatch.setattr(routes.kodewaves_db_client, "get_setting", AsyncMock(
        return_value={"enable_local_ai_engine": True}))
    monkeypatch.setattr(routes.kodewaves_db_client, "get_org_ai_policy", AsyncMock(return_value=None))
    monkeypatch.setattr(routes.kodewaves_db_client, "list_voices", AsyncMock(return_value=[]))
    monkeypatch.setattr(routes.master_credential_service, "get_master_credential", AsyncMock(return_value=None))
    monkeypatch.setattr("api.services.catalog.local_inventory.get_installed_piper_voices", AsyncMock(
        return_value={"hi_IN-pratham-medium": {}, "en_US-lessac-medium": {}}))
    result = await routes.get_voices("piper", user=SimpleNamespace(selected_organization_id=1))
    assert {v.voice_id for v in result.voices} == {"hi_IN-pratham-medium", "en_US-lessac-medium"}
    assert result.facets.languages == ["en", "hi"]
