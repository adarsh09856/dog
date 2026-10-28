import pytest

from api.services.pipecat.speaches_tts import SpeachesLiveTTSService
from pipecat.frames.frames import ErrorFrame, TTSAudioRawFrame, TTSStoppedFrame
from pipecat.services.speaches.tts import SpeachesTTSSettings


@pytest.mark.asyncio
async def test_failed_final_phrase_still_closes_http_audio_context():
    service = SpeachesLiveTTSService(
        api_key="test",
        base_url="http://localhost:8000/v1",
        settings=SpeachesTTSSettings(model="indic-vits-rasa-13", voice="HIN_F"),
    )
    try:
        service._turn_context_id = "turn-1"
        await service.create_audio_context("turn-1")
        queue = service._audio_contexts["turn-1"]
        await queue.put(TTSAudioRawFrame(audio=b"\x01\x00", sample_rate=24000, num_channels=1))
        await queue.put(ErrorFrame("final phrase produced no audio", fatal=False))
        service._is_yielding_frames_synchronously = False

        await service.on_turn_context_completed()

        queued = [queue.get_nowait(), queue.get_nowait(), queue.get_nowait(), queue.get_nowait()]
        assert isinstance(queued[0], TTSAudioRawFrame)
        assert isinstance(queued[1], ErrorFrame)
        assert isinstance(queued[2], TTSStoppedFrame)
        assert queued[3] is None
        assert service._turn_context_id is None
    finally:
        await service._client.close()
