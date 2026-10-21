import numpy as np
import asyncio
import threading
from contextlib import suppress
import pytest
from fastapi.testclient import TestClient

from api.local_models.indus_tts import app as indus_tts


def test_indus_model_metadata_only_advertises_its_supported_languages(monkeypatch):
    monkeypatch.setattr(indus_tts, "MODEL", object())

    response = TestClient(indus_tts.app).get("/v1/models")

    assert response.status_code == 200
    model = response.json()["data"][0]
    assert model["id"] == "indus-pocket-tts"
    assert model["task"] == "text-to-speech"
    assert model["languages"] == ["hi-IN", "en-IN"]
    assert [voice["id"] for voice in model["voices"]] == ["Inaya"]


def test_indus_tts_streams_24khz_pcm_and_rejects_unknown_voice(monkeypatch):
    monkeypatch.setattr(indus_tts, "_load_model", lambda: None)
    monkeypatch.setattr(indus_tts, "_warm_model", lambda: None)
    monkeypatch.setattr(indus_tts, "MODEL", object())
    monkeypatch.setattr(indus_tts, "VOICE", object())

    class FakeTensor:
        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return np.array([0.0, 0.5, -0.5], dtype=np.float32)

    def fake_stream(_model, _voice, _text):
        yield FakeTensor()

    monkeypatch.setattr(indus_tts, "_stream_speech", fake_stream, raising=False)

    with TestClient(indus_tts.app) as client:
        response = client.post(
            "/v1/audio/speech",
            json={"model": "indus-pocket-tts", "voice": "Inaya", "input": "नमस्ते"},
        )
        invalid_voice = client.post(
            "/v1/audio/speech",
            json={"model": "indus-pocket-tts", "voice": "hf_alpha", "input": "hello"},
        )

    expected = (np.array([0.0, 0.5, -0.5]) * 32767.0).astype("<i2").tobytes()
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/pcm"
    assert response.content == expected
    assert invalid_voice.status_code == 400


@pytest.mark.asyncio
async def test_indus_lifespan_warms_bilingual_voice_after_loading(monkeypatch):
    events = []
    monkeypatch.setattr(indus_tts, "_load_model", lambda: events.append("load"))
    monkeypatch.setattr(indus_tts, "_warm_model", lambda: events.append("warm"))

    async with indus_tts.lifespan(indus_tts.app):
        assert events == ["load", "warm"]


def test_indus_speaks_after_internal_hindi_sentence_mark():
    assert indus_tts._prepare_speech_text(
        "नमस्ते। बताइए, मैं आपकी किस तरह मदद करूँ?"
    ) == "नमस्ते, बताइए, मैं आपकी किस तरह मदद करूँ?"
    assert indus_tts._prepare_speech_text("नमस्ते।") == "नमस्ते।"


@pytest.mark.parametrize('response_format', ['pcm', 'wav'])
def test_empty_tts_is_an_http_error_instead_of_a_successful_silent_stream(monkeypatch, response_format):
    monkeypatch.setattr(indus_tts, 'MODEL', object())
    monkeypatch.setattr(indus_tts, '_stream_speech', lambda *args: iter(()))
    response = TestClient(indus_tts.app).post('/v1/audio/speech', json={
        'input': 'test', 'response_format': response_format,
    })
    assert response.status_code == 502
    assert response.json()['detail'] == 'Local TTS returned no audio'


@pytest.mark.asyncio
async def test_cancelled_inference_finishes_and_closes_before_next_request(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    closed = threading.Event()
    second_entered = threading.Event()
    monkeypatch.setattr(indus_tts, 'MODEL', object())
    monkeypatch.setattr(indus_tts, 'SYNTHESIS_LOCK', asyncio.Lock())

    class Tensor:
        def detach(self): return self
        def cpu(self): return self
        def numpy(self): return np.array([0.1], dtype=np.float32)

    def generate(model, voice, text):
        if text == 'first':
            try:
                entered.set()
                assert release.wait(5)
                yield Tensor()
            finally:
                closed.set()
        else:
            second_entered.set()
            assert closed.is_set()
            yield Tensor()

    monkeypatch.setattr(indus_tts, '_stream_speech', generate)
    first = asyncio.create_task(indus_tts.speech(indus_tts.SpeechRequest(input='first')))
    assert await asyncio.to_thread(entered.wait, 2)
    first.cancel()
    second = asyncio.create_task(indus_tts.speech(indus_tts.SpeechRequest(input='second')))
    try:
        await asyncio.sleep(0.05)
        assert not second_entered.is_set()
    finally:
        release.set()
    with suppress(asyncio.CancelledError):
        await first
    response = await asyncio.wait_for(second, 3)
    audio = b''.join([chunk async for chunk in response.body_iterator])
    assert audio
    assert closed.is_set()
    assert second_entered.is_set()
