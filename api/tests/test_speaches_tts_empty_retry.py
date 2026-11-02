import pytest

from api.services.pipecat.speaches_tts import SpeachesLiveTTSService
from pipecat.frames.frames import ErrorFrame, TTSAudioRawFrame
from pipecat.services.speaches.tts import SpeachesTTSService, SpeachesTTSSettings


def _service() -> SpeachesLiveTTSService:
    return SpeachesLiveTTSService(
        api_key="test",
        base_url="http://localhost:8000/v1",
        sample_rate=24000,
        settings=SpeachesTTSSettings(model="kokoro", voice="hf_alpha"),
    )


@pytest.mark.asyncio
async def test_standard_speaches_retries_one_empty_success(monkeypatch):
    calls = []

    async def synthesize(self, text, context_id):
        calls.append(text)
        if len(calls) == 2:
            yield TTSAudioRawFrame(
                audio=b"\x01\x00" * 240,
                sample_rate=self.sample_rate,
                num_channels=1,
                context_id=context_id,
            )

    monkeypatch.setattr(SpeachesTTSService, "run_tts", synthesize)
    service = _service()
    try:
        frames = [frame async for frame in service.run_tts("नमस्ते", "empty-then-audio")]
        assert calls == ["नमस्ते", "नमस्ते"]
        assert sum(isinstance(frame, TTSAudioRawFrame) for frame in frames) == 1
        assert not any(isinstance(frame, ErrorFrame) for frame in frames)
    finally:
        await service._client.close()


@pytest.mark.asyncio
async def test_standard_speaches_reports_empty_stream_after_single_retry(monkeypatch):
    calls = []

    async def synthesize(self, text, context_id):
        calls.append(text)
        if False:
            yield None

    monkeypatch.setattr(SpeachesTTSService, "run_tts", synthesize)
    service = _service()
    try:
        frames = [frame async for frame in service.run_tts("नमस्ते", "still-empty")]
        assert calls == ["नमस्ते", "नमस्ते"]
        assert len(frames) == 1 and isinstance(frames[0], ErrorFrame)
        assert "no audio after one retry" in frames[0].error
    finally:
        await service._client.close()


@pytest.mark.asyncio
async def test_standard_speaches_does_not_retry_provider_error(monkeypatch):
    calls = []

    async def synthesize(self, text, context_id):
        calls.append(text)
        yield ErrorFrame("provider HTTP 503")

    monkeypatch.setattr(SpeachesTTSService, "run_tts", synthesize)
    service = _service()
    try:
        frames = [frame async for frame in service.run_tts("नमस्ते", "provider-error")]
        assert calls == ["नमस्ते"]
        assert len(frames) == 1 and isinstance(frames[0], ErrorFrame)
        assert frames[0].error == "provider HTTP 503"
    finally:
        await service._client.close()


@pytest.mark.asyncio
async def test_standard_speaches_does_not_replay_after_partial_audio(monkeypatch):
    calls = []

    async def synthesize(self, text, context_id):
        calls.append(text)
        yield TTSAudioRawFrame(
            audio=b"\x01\x00" * 240,
            sample_rate=self.sample_rate,
            num_channels=1,
            context_id=context_id,
        )

    monkeypatch.setattr(SpeachesTTSService, "run_tts", synthesize)
    service = _service()
    try:
        frames = [frame async for frame in service.run_tts("नमस्ते", "partial-audio")]
        audio = [frame for frame in frames if isinstance(frame, TTSAudioRawFrame)]
        assert calls == ["नमस्ते"]
        assert len(audio) == 1 and audio[0].audio == b"\x01\x00" * 240
        assert not any(isinstance(frame, ErrorFrame) for frame in frames)
    finally:
        await service._client.close()
