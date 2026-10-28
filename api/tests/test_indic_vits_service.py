"""Exercise regional speech HTTP contracts without downloading native weights."""
import asyncio
import importlib.util
import io
import sys
import threading
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import numpy as np
import pytest


@pytest.fixture
def regional(monkeypatch):
    monkeypatch.setitem(sys.modules, "sherpa_onnx", SimpleNamespace(GenerationConfig=SimpleNamespace))
    path = Path(__file__).parents[1] / "local_models" / "indic_vits" / "app.py"
    spec = importlib.util.spec_from_file_location("regional_voice_test_app", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.MODEL = SimpleNamespace(generate=Mock(return_value=SimpleNamespace(
        sample_rate=24000, samples=np.array([-1, 0, 1], dtype=np.float32))))
    yield module
    module.WORKER.shutdown(wait=True)


@pytest.mark.asyncio
async def test_inventory_exposes_only_trained_speakers_and_actual_languages(regional):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=regional.app), base_url="http://test") as client:
        response = await client.get("/v1/models")
    model = response.json()["data"][0]
    assert model["installed"] is True
    assert model["streaming"] is True
    assert model["streaming_granularity"] == "sentence"
    assert len(model["languages"]) == 13
    assert len(model["voices"]) == 20
    assert "hi-IN" not in model["languages"] and "en-IN" not in model["languages"]
    speakers = {item["id"]: item for item in model["voices"]}
    assert speakers["MAR_M"]["gender"] == "male"
    assert speakers["TAM_F"]["languages"] == ["ta-IN"]


@pytest.mark.asyncio
@pytest.mark.parametrize("format", ["pcm", "wav"])
async def test_speech_keeps_selected_speaker_speed_and_exact_pcm(regional, format):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=regional.app), base_url="http://test") as client:
        response = await client.post("/v1/audio/speech", json={
            "voice": "MAR_M", "input": "नमस्कार।", "speed": 0.8, "response_format": format})
    assert response.status_code == 200
    text, config = regional.MODEL.generate.call_args.args[:2]
    assert text == "नमस्कार"
    assert config.sid == 13 and config.speed == 0.8
    assert config.extra == {"emotion_id": "4"}
    pcm = response.content
    if format == "wav":
        with wave.open(io.BytesIO(pcm), "rb") as wav:
            assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (24000, 1, 2)
            pcm = wav.readframes(wav.getnframes())
    assert pcm == np.array([-32767, 0, 32767], dtype="<i2").tobytes()


@pytest.mark.asyncio
@pytest.mark.parametrize("preferred,text,expected_sid", [
    ("KAN_F", "ನಮಸ್ಕಾರ", 8),
    ("KAN_F", "ನಮಸ್ಕಾರ, hello", 8),
    ("KAN_F", "வணக்கம்", 18),
    ("KAN_M", "ਸਤ ਸ੍ਰੀ ਅਕਾਲ", 16),
    ("MAR_M", "नमस्कार", 13),  # Shared Devanagari remains ambiguous.
])
async def test_live_speech_routes_unambiguous_script_and_preserves_gender(
    regional, preferred, text, expected_sid,
):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=regional.app), base_url="http://test") as client:
        response = await client.post("/v1/audio/speech", json={"voice": preferred, "input": text})
    assert response.status_code == 200
    assert regional.MODEL.generate.call_args.args[1].sid == expected_sid


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,status", [
    ({"voice": "default", "input": "नमस्कार"}, 400),
    ({"voice": "Inaya", "input": "नमस्कार"}, 400),
    ({"voice": "MAR_M", "input": "..."}, 400),
    ({"model": "other", "voice": "MAR_M", "input": "नमस्कार"}, 404),
    ({"voice": "MAR_M", "input": "नमस्कार", "response_format": "mp3"}, 400),
])
async def test_invalid_requests_never_synthesize_or_substitute_voice(regional, payload, status):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=regional.app), base_url="http://test") as client:
        response = await client.post("/v1/audio/speech", json=payload)
    assert response.status_code == status
    regional.MODEL.generate.assert_not_called()


@pytest.mark.asyncio
async def test_cancelled_request_holds_native_inference_lock_until_work_finishes(regional):
    entered, release = threading.Event(), threading.Event()
    native = regional.MODEL.generate
    def blocked(*args):
        entered.set()
        assert release.wait(3)
        return SimpleNamespace(sample_rate=24000, samples=np.zeros(24, dtype=np.float32))
    native.side_effect = blocked
    request = regional.SpeechRequest(voice="MAR_F", input="नमस्कार", response_format="wav")
    first = asyncio.create_task(regional.speech(request))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        first.cancel()
        second = asyncio.create_task(regional.speech(request))
        await asyncio.sleep(0)
        assert regional.LOCK.locked()
        assert native.call_count == 1
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(first, 2)
        assert (await asyncio.wait_for(second, 2)).status_code == 200
        assert native.call_count == 2
    finally:
        release.set()
        if not first.done():
            first.cancel()


@pytest.mark.asyncio
async def test_pcm_releases_callback_audio_before_native_generation_finishes(regional):
    release = threading.Event()
    def generate(text, config, callback):
        assert callback(np.array([0.5], dtype=np.float32), 0.5) == 1
        assert release.wait(3)
        assert callback(np.array([-0.5], dtype=np.float32), 1.0) == 1
        return SimpleNamespace(sample_rate=24000, samples=np.array([0.5, -0.5], dtype=np.float32))
    regional.MODEL.generate.side_effect = generate
    response = await regional.speech(regional.SpeechRequest(voice="KAN_F", input="ನಮಸ್ಕಾರ"))
    iterator = response.body_iterator
    try:
        first = await asyncio.wait_for(anext(iterator), 2)
        assert first == np.array([16383], dtype="<i2").tobytes()
        assert regional.LOCK.locked()
        release.set()
        rest = b"".join([chunk async for chunk in iterator])
        assert rest == np.array([-16383], dtype="<i2").tobytes()
        assert not regional.LOCK.locked()
    finally:
        release.set()
        await iterator.aclose()


@pytest.mark.asyncio
async def test_pcm_disconnect_stops_callback_and_holds_lock_until_native_exit(regional):
    release = threading.Event()
    callback_results = []
    def generate(text, config, callback):
        callback_results.append(callback(np.ones(24, dtype=np.float32), 0.5))
        assert release.wait(3)
        callback_results.append(callback(np.ones(24, dtype=np.float32), 1.0))
        return SimpleNamespace(sample_rate=24000, samples=np.ones(48, dtype=np.float32))
    regional.MODEL.generate.side_effect = generate
    response = await regional.speech(regional.SpeechRequest(voice="KAN_F", input="ನಮಸ್ಕಾರ"))
    iterator = response.body_iterator
    await asyncio.wait_for(anext(iterator), 2)
    closing = asyncio.create_task(iterator.aclose())
    try:
        await asyncio.sleep(0)
        assert regional.LOCK.locked()
        assert not closing.done()
        release.set()
        await asyncio.wait_for(closing, 2)
        assert callback_results == [1, 0]
        assert not regional.LOCK.locked()
    finally:
        release.set()
