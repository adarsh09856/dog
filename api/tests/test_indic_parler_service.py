"""Transport contracts only; these tests do not certify model audio or latency."""
import asyncio
import io
import threading
import wave
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.local_models.indic_parler import app as service


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch):
    monkeypatch.setattr(service, "RUNTIME", None)
    monkeypatch.setattr(service, "SYNTHESIS_LOCK", asyncio.Lock())


@pytest.mark.asyncio
async def test_unloaded_model_is_not_advertised_and_speech_fails():
    assert (await service.models())["data"] == []
    with pytest.raises(HTTPException) as error:
        await service.speech(service.SpeechRequest(input="Hello"))
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_pcm_is_delivered_before_generation_finishes_and_disconnect_stops_worker(monkeypatch):
    finished = threading.Event()

    def generate(request, emit, stopped):
        emit(b"\x01\x00" * 2400)
        stopped.wait(timeout=2)
        finished.set()

    monkeypatch.setattr(service, "RUNTIME", SimpleNamespace(generate=generate))
    stream = service.pcm_stream(service.SpeechRequest(input="Hello"))
    first = await asyncio.wait_for(anext(stream), timeout=1)
    assert first == b"\x01\x00" * 2400
    assert not finished.is_set()
    assert service.SYNTHESIS_LOCK.locked()
    await stream.aclose()
    assert finished.is_set()
    assert not service.SYNTHESIS_LOCK.locked()


@pytest.mark.asyncio
async def test_busy_model_rejects_second_utterance_without_a_hidden_queue(monkeypatch):
    def generate(request, emit, stopped):
        emit(b"\x01\x00")
        stopped.wait(timeout=2)

    monkeypatch.setattr(service, "RUNTIME", SimpleNamespace(generate=generate))
    stream = service.pcm_stream(service.SpeechRequest(input="First"))
    await anext(stream)
    try:
        with pytest.raises(HTTPException) as error:
            await service.speech(service.SpeechRequest(input="Second"))
        assert error.value.status_code == 429
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_generation_failure_before_audio_is_http_error_and_releases_lock(monkeypatch):
    def generate(*args):
        raise ValueError("internal model detail must not reach callers")

    monkeypatch.setattr(service, "RUNTIME", SimpleNamespace(generate=generate))
    with pytest.raises(HTTPException) as error:
        await service.speech(service.SpeechRequest(input="Hello"))
    assert error.value.status_code == 502
    assert "internal model detail" not in error.value.detail
    assert not service.SYNTHESIS_LOCK.locked()


@pytest.mark.asyncio
async def test_wav_contains_all_pcm_at_adapter_sample_rate(monkeypatch):
    expected = b"\x01\x00" * 100 + b"\xff\x7f" * 100

    def generate(request, emit, stopped):
        emit(expected[:200])
        emit(expected[200:])

    monkeypatch.setattr(service, "RUNTIME", SimpleNamespace(generate=generate))
    response = await service.speech(service.SpeechRequest(input="Hello", response_format="wav"))
    with wave.open(io.BytesIO(response.body), "rb") as audio:
        assert audio.getframerate() == 24000
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.readframes(audio.getnframes()) == expected


@pytest.mark.asyncio
async def test_language_metadata_distinguishes_official_and_experimental_support(monkeypatch):
    monkeypatch.setattr(service, "RUNTIME", object())
    model = (await service.models())["data"][0]
    assert {"hi-IN", "en-IN", "kn-IN"} <= set(model["languages"])
    assert set(model["experimental_languages"]) == {"pa-IN", "ks-IN"}
    assert len(model["languages"]) == 21
    assert all(voice["languages"] == model["languages"] for voice in model["voices"])
    assert {voice["gender"] for voice in model["voices"]} == {"male", "female"}
