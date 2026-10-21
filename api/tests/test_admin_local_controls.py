"""Admin controls must reflect the local engine's actual state and failures."""
import io
import wave
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.routes.admin import settings


class Response:
    def __init__(self, status=200, data=None, audio=b""):
        self.status, self.data, self.audio = status, data, audio

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self.data

    async def read(self):
        return self.audio


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr(settings.kodewaves_db_client, "get_setting", AsyncMock(return_value={}))
    monkeypatch.setattr(settings.catalog_service, "notify_changed", AsyncMock())

    def configure(response):
        class Session(Response):
            def get(self, *args, **kwargs):
                return response

            post = delete = get

        monkeypatch.setattr("aiohttp.ClientSession", lambda **kwargs: Session())

    return configure


@pytest.mark.asyncio
@pytest.mark.parametrize("data,expected", [
    ({"voices": []}, []),
    ({"voices": {"missing": {"installed": False}, "present": {}}}, ["present"]),
    (["en_US-lessac-medium"], ["en_US-lessac-medium"]),
    ({"voices": [{"id": "missing", "installed": False}, {"id": "present"}]}, ["present"]),
])
async def test_installed_voices_are_not_invented(engine, data, expected):
    engine(Response(data=data))
    result = await settings.get_piper_voices()
    assert [voice["id"] for voice in result["voices"]] == expected


@pytest.mark.asyncio
async def test_failed_voice_inventory_is_not_online(engine):
    engine(Response(status=503))
    result = await settings.get_piper_voices()
    assert result["voices"] == []
    assert result["status"] == "HTTP 503"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["download", "delete"])
async def test_failed_mutations_do_not_report_success(engine, operation):
    engine(Response(status=500))
    with pytest.raises(HTTPException) as error:
        if operation == "download":
            await settings.download_piper_voice(settings.PiperDownloadRequest(voice="test"))
        else:
            await settings.delete_piper_voice("test")
    assert error.value.status_code == 502


@pytest.mark.asyncio
async def test_audio_metrics_use_wav_header(engine):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0\0" * 8000)
    engine(Response(audio=output.getvalue()))
    result = await settings.test_piper_voice({"voice": "en_US-lessac-medium"})
    assert result["success"] is True
    assert result["sample_rate"] == 16000
    assert result["duration_s"] == 0.5


@pytest.mark.asyncio
async def test_whisper_download_uses_model_path(monkeypatch):
    monkeypatch.setattr(settings.catalog_service, "notify_changed", AsyncMock())
    monkeypatch.setattr(settings, "normalize_local_ai_endpoint", lambda url: url)
    monkeypatch.setattr(settings.kodewaves_db_client, "get_setting", AsyncMock(
        return_value={"whisper_endpoint": "http://whisper:8000"}))
    calls = []

    class Session(Response):
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response(status=200)

    monkeypatch.setattr("aiohttp.ClientSession", lambda **kwargs: Session())
    await settings.download_whisper_model({"model": "Systran/faster-whisper-base"})
    assert calls == [("http://whisper:8000/v1/models/Systran/faster-whisper-base", {})]


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['ollama', 'piper', 'whisper'])
async def test_model_removal_refreshes_catalog_on_every_worker(engine, kind):
    engine(Response(status=200))
    operation = {'ollama': settings.delete_ollama_model,
                 'piper': settings.delete_piper_voice,
                 'whisper': settings.delete_whisper_model}[kind]
    await operation('test-model')
    settings.catalog_service.notify_changed.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_model_removal_does_not_announce_inventory_change(engine):
    engine(Response(status=502))
    with pytest.raises(HTTPException):
        await settings.delete_whisper_model('test-model')
    settings.catalog_service.notify_changed.assert_not_awaited()
