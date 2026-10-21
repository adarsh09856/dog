import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPER_DATA_DIR", str(tmp_path))
    path = Path(__file__).resolve().parents[2] / "scripts/local_ai_server.py"
    spec = importlib.util.spec_from_file_location("local_runner_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_whisper_lifecycle_reports_actual_loaded_state(runner, monkeypatch):
    def load(name):
        runner.LOADED_WHISPER_MODELS[name] = object()
    monkeypatch.setattr(runner, "get_whisper_model", load)
    async with AsyncClient(transport=ASGITransport(app=runner.whisper_app), base_url="http://test") as client:
        data = (await client.get('/v1/models')).json()['data']
        assert not any(item['installed'] for item in data)
        assert all(item['task'] == 'automatic-speech-recognition' for item in data)
        assert (await client.post('/v1/models', json={'model': 'Systran/faster-whisper-tiny'})).status_code == 200
        assert (await client.post('/v1/models/Systran/faster-whisper-base')).status_code == 200
        data = (await client.get('/v1/models')).json()['data']
        assert {item['id'] for item in data if item['installed']} == {
            'Systran/faster-whisper-tiny', 'Systran/faster-whisper-base'
        }
        assert (await client.delete('/v1/models/Systran/faster-whisper-base')).status_code == 200
        assert set(runner.LOADED_WHISPER_MODELS) == {'tiny'}
        assert (await client.post('/v1/models', json={'model': 'invented-model'})).status_code == 400


@pytest.mark.asyncio
async def test_voice_delete_evicts_cache_and_rejects_path_input(runner):
    runner.LOADED_PIPER_VOICES['voice'] = object()
    (runner.VOICE_DIR / 'voice.onnx').write_bytes(b'synthetic')
    (runner.VOICE_DIR / 'voice.onnx.json').write_text('{}')
    async with AsyncClient(transport=ASGITransport(app=runner.piper_app), base_url="http://test") as client:
        assert (await client.delete('/voices/voice')).status_code == 200
        assert not runner.LOADED_PIPER_VOICES
        assert not list(runner.VOICE_DIR.iterdir())
    with pytest.raises(Exception) as error:
        runner.validate_voice_id('../outside')
    assert error.value.status_code == 400


def test_missing_voice_is_never_substituted(runner, monkeypatch):
    import sys
    load = Mock()
    monkeypatch.setitem(sys.modules, 'piper', NS(PiperVoice=NS(load=load)))
    (runner.VOICE_DIR / 'different.onnx').write_bytes(b'synthetic')
    with pytest.raises(Exception) as error:
        runner.get_piper_voice('requested')
    assert error.value.status_code == 404
    load.assert_not_called()


@pytest.mark.asyncio
async def test_cancelled_transcription_keeps_file_until_worker_finishes(runner, monkeypatch):
    import asyncio
    import threading
    from starlette.datastructures import UploadFile
    import io

    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    paths = []
    def transcribe(path, **kwargs):
        paths.append(Path(path))
        started.set()
        release.wait(5)
        try:
            assert paths[0].read_bytes() == b"test-audio"
            return [NS(text="hello")], NS(language="en", language_probability=1, duration=1)
        finally:
            finished.set()
    monkeypatch.setattr(runner, "get_whisper_model", lambda name: NS(transcribe=transcribe))
    request = asyncio.create_task(runner.transcribe_audio(UploadFile(io.BytesIO(b"test-audio")), "tiny", "en"))
    try:
        assert await asyncio.to_thread(started.wait, 3)
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        assert paths[0].exists()
    finally:
        release.set()
    assert await asyncio.to_thread(finished.wait, 3)
    for _ in range(100):
        if not paths[0].exists():
            break
        await asyncio.sleep(0.01)
    assert not paths[0].exists()
