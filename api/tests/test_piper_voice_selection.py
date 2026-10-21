import pytest

from pipecat.frames.frames import ErrorFrame, TTSAudioRawFrame
from pipecat.services.piper.tts import PiperHttpTTSService, PiperHttpTTSSettings


@pytest.mark.asyncio
async def test_missing_piper_voice_cannot_silently_fall_back():
    class Inventory:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def json(self):
            return {"hi_IN-pratham-medium": {}}

    class Session:
        def get(self, url, **kwargs):
            assert url == "http://piper:5000/voices"
            return Inventory()

        def post(self, *args, **kwargs):
            raise AssertionError("An uninstalled voice must never be synthesized")

    service = PiperHttpTTSService(
        base_url="http://piper:5000/synthesize", aiohttp_session=Session(),
        settings=PiperHttpTTSSettings(voice="fr_FR-missing-medium"),
    )
    frames = [frame async for frame in service.run_tts("Hello", "test")]
    assert len(frames) == 1
    assert isinstance(frames[0], ErrorFrame)
    assert "not installed" in frames[0].error


@pytest.mark.asyncio
@pytest.mark.parametrize("speed,expected_scale", [(1.0, 1.0), (1.25, 0.8)])
async def test_selected_piper_speed_reaches_synthesis(speed, expected_scale):
    class Response:
        status = 400

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def text(self):
            return "Test response"

    class Session:
        def post(self, url, **kwargs):
            assert kwargs["json"]["voice"] == "en_US-lessac-medium"
            assert kwargs["json"]["length_scale"] == expected_scale
            return Response()

    service = PiperHttpTTSService(
        base_url="http://piper:5000/synthesize", aiohttp_session=Session(),
        settings=PiperHttpTTSSettings(voice="en_US-lessac-medium", speed=speed),
    )
    service._validated_voice = "en_US-lessac-medium"
    frames = [frame async for frame in service.run_tts("Hello", "test")]
    assert any(isinstance(frame, ErrorFrame) for frame in frames)


@pytest.mark.asyncio
@pytest.mark.parametrize("speed", [0, -1, float("nan"), float("inf")])
async def test_invalid_speed_cannot_start_synthesis(speed):
    class Session:
        def post(self, *args, **kwargs):
            raise AssertionError("Invalid speech speed must never reach synthesis")

    service = PiperHttpTTSService(
        base_url="http://piper:5000/synthesize", aiohttp_session=Session(),
        settings=PiperHttpTTSSettings(voice="en_US-lessac-medium", speed=speed),
    )
    service._validated_voice = "en_US-lessac-medium"
    frames = [frame async for frame in service.run_tts("Hello", "test")]
    assert len(frames) == 1 and isinstance(frames[0], ErrorFrame)
    assert "positive and finite" in frames[0].error


@pytest.mark.asyncio
async def test_call_owned_piper_session_closes_even_if_parent_cleanup_fails(monkeypatch):
    from unittest.mock import AsyncMock
    from api.services.pipecat.piper_tts import PiperOwnedSessionTTSService
    session = type("Session", (), {"closed": False, "close": AsyncMock()})()
    monkeypatch.setattr(PiperHttpTTSService, "cleanup", AsyncMock(side_effect=RuntimeError("cleanup failed")))
    service = PiperOwnedSessionTTSService(base_url="http://piper:5000/synthesize", aiohttp_session=session)
    with pytest.raises(RuntimeError, match="cleanup failed"):
        await service.cleanup()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_call_owned_piper_does_not_close_an_already_closed_session(monkeypatch):
    from unittest.mock import AsyncMock
    from api.services.pipecat.piper_tts import PiperOwnedSessionTTSService
    session = type("Session", (), {"closed": True, "close": AsyncMock()})()
    monkeypatch.setattr(PiperHttpTTSService, "cleanup", AsyncMock())
    service = PiperOwnedSessionTTSService(base_url="http://piper:5000/synthesize", aiohttp_session=session)
    await service.cleanup()
    session.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_call_owned_piper_recovers_when_first_request_has_no_audio(monkeypatch):
    from api.services.pipecat.piper_tts import PiperOwnedSessionTTSService

    calls = []

    async def synthesize(_service, text, context_id):
        calls.append((text, context_id))
        if len(calls) == 1:
            yield ErrorFrame(error="temporary voice-server failure")
        else:
            yield TTSAudioRawFrame(
                audio=b"\x01\x00" * 160,
                sample_rate=8000,
                num_channels=1,
                context_id=context_id,
            )

    monkeypatch.setattr(PiperHttpTTSService, "run_tts", synthesize)
    service = PiperOwnedSessionTTSService(
        base_url="http://piper:5000/synthesize",
        aiohttp_session=object(),
        settings=PiperHttpTTSSettings(voice="en_US-lessac-medium"),
    )
    frames = [frame async for frame in service.run_tts("Hello", "test")]

    assert calls == [("Hello", "test"), ("Hello", "test")]
    assert len(frames) == 1 and isinstance(frames[0], TTSAudioRawFrame)
    assert service._validated_voice == "en_US-lessac-medium"
