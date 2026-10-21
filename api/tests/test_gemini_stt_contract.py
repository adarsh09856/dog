from types import SimpleNamespace as NS

import pytest
from pipecat.frames.frames import ErrorFrame, TranscriptionFrame
from api.services.pipecat import gemini_stt


class Response:
    def __init__(self, status): self.status = status
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    async def json(self): return {"candidates": [{"content": {"parts": [{"text": "मुझे appointment चाहिए"}]}}]}


class Session:
    def __init__(self, status=200): self.status = status; self.request = None
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    def post(self, url, **kwargs):
        self.request = (url, kwargs)
        return Response(self.status)


@pytest.mark.asyncio
async def test_explicit_model_and_multilingual_transcript_are_preserved(monkeypatch):
    session = Session()
    monkeypatch.setattr(gemini_stt.aiohttp, "ClientSession", lambda **kwargs: session)
    service = gemini_stt.GeminiSTTService(api_key="synthetic-key", model="gemini-2.5-flash", language="multi")
    frames = [f async for f in service.run_stt(bytes(3200))]
    assert isinstance(frames[0], TranscriptionFrame)
    assert frames[0].text == "मुझे appointment चाहिए"
    assert "gemini-2.5-flash:" in session.request[0]
    assert "synthetic-key" not in session.request[0]
    assert session.request[1]["headers"]["x-goog-api-key"] == "synthetic-key"


@pytest.mark.asyncio
async def test_provider_failure_is_visible_instead_of_silence(monkeypatch):
    session = Session(429)
    monkeypatch.setattr(gemini_stt.aiohttp, "ClientSession", lambda **kwargs: session)
    service = gemini_stt.GeminiSTTService(api_key="synthetic-key")
    frames = [f async for f in service.run_stt(bytes(3200))]
    assert len(frames) == 1 and isinstance(frames[0], ErrorFrame)
    assert "429" in frames[0].error


@pytest.mark.asyncio
async def test_missing_key_is_visible_to_pipeline():
    frames = [f async for f in gemini_stt.GeminiSTTService().run_stt(bytes(3200))]
    assert isinstance(frames[0], ErrorFrame)
