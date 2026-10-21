"""Gemini 3.8 TTS streams raw audio frames to the caller as events arrive."""

import base64
import json

import pytest
from pipecat.frames.frames import TTSAudioRawFrame

from api.services.pipecat import gemini_tts


class _SseContent:
    def __init__(self, events):
        self._events = iter(events)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._events)
        except StopIteration:
            raise StopAsyncIteration


class _Response:
    status = 200

    def __init__(self, events):
        self.content = _SseContent(events)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _Session:
    def __init__(self, response):
        self.response = response
        self.request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, **kwargs):
        self.request = (url, kwargs)
        return self.response


@pytest.mark.asyncio
@pytest.mark.parametrize('transport_rate', [8000, 16000, 24000])
async def test_gemini_38_streams_pcm_using_the_selected_voice(monkeypatch, transport_rate):
    pcm = b"\x01\x00\x02\x00"
    event = {
        "candidates": [{
            "content": {"parts": [{
                "inlineData": {
                    "mimeType": "audio/l16; rate=24000; channels=1",
                    "data": base64.b64encode(pcm).decode(),
                }
            }]}
        }]
    }
    session = _Session(_Response([b"data: " + json.dumps(event).encode() + b"\n\n"]))
    monkeypatch.setattr(gemini_tts.aiohttp, "ClientSession", lambda: session)
    service = gemini_tts.GeminiTTSService(
        api_key="test-key", model="gemini-3.8-flash-lite-tts", voice="Kore", sample_rate=transport_rate
    )

    frames = [frame async for frame in service.run_tts("नमस्ते", "ctx")]

    audio_frames = [frame for frame in frames if isinstance(frame, TTSAudioRawFrame)]
    assert len(audio_frames) == 1
    assert audio_frames[0].audio == pcm
    assert audio_frames[0].sample_rate == 24000
    url, request = session.request
    assert url.endswith(":streamGenerateContent?alt=sse")
    assert "test-key" not in url
    assert request["headers"]["x-goog-api-key"] == "test-key"
    assert request["json"]["generationConfig"]["speechConfig"]["voiceConfig"] == {
        "voice": "Kore"
    }
    assert request["json"]["generationConfig"]["responseFormat"]["audio"]["mimeType"] == "AUDIO_L16"
    assert request["json"]["generationConfig"]["responseFormat"]["audio"]["sampleRate"] == 24000
