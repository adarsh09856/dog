import asyncio
from contextlib import suppress

import pytest

from api.services.pipecat.speaches_tts import SpeachesLiveTTSService
from pipecat.clocks.system_clock import SystemClock
from pipecat.frames.frames import (
    CancelFrame, EndFrame, ErrorFrame, LLMFullResponseStartFrame,
    TTSAudioRawFrame, TTSStoppedFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessorSetup
from pipecat.services.speaches.tts import SpeachesTTSSettings
from pipecat.utils.asyncio.task_manager import TaskManager


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

        # Pipecat sets this flag from the final phrase, which had no PCM.
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


@pytest.mark.asyncio
async def test_graceful_end_consumes_pending_final_pcm_before_end_frame():
    service = SpeachesLiveTTSService(
        api_key="test", base_url="http://localhost:8000/v1",
        settings=SpeachesTTSSettings(model="indic-vits-rasa-13", voice="HIN_F"),
    )
    emitted = []
    worker_alive_at_synthesis = []

    async def push(frame, direction=FrameDirection.DOWNSTREAM):
        emitted.append(frame)

    async def synthesize(text, context_id):
        worker_alive_at_synthesis.append(service._audio_context_task is not None)
        yield TTSAudioRawFrame(b"\x01\x00" * 240, 24000, 1, context_id=context_id)
        await asyncio.sleep(0)
        yield TTSAudioRawFrame(b"\x02\x00" * 240, 24000, 1, context_id=context_id)

    service.push_frame = push
    service.run_tts = synthesize
    await service.setup(FrameProcessorSetup(
        clock=SystemClock(), task_manager=TaskManager(), pipeline_worker=None,
    ))
    service._audio_contexts = {}
    service._audio_context_task = asyncio.create_task(service._audio_context_task_handler())
    try:
        await service.process_frame(LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM)
        async for _ in service._text_aggregator.aggregate("A short pending final phrase"):
            pass
        await asyncio.wait_for(service.process_frame(EndFrame(), FrameDirection.DOWNSTREAM), timeout=1)
        assert worker_alive_at_synthesis == [True]
        audio = [frame for frame in emitted if isinstance(frame, TTSAudioRawFrame)]
        assert b"".join(frame.audio for frame in audio) == b"\x01\x00" * 240 + b"\x02\x00" * 240
        assert isinstance(emitted[-1], EndFrame)
        assert any(isinstance(frame, TTSStoppedFrame) for frame in emitted[:-1])
        assert service._audio_context_task is None
    finally:
        await service._stop_turn_keepalive()
        if service._audio_context_task:
            service._audio_context_task.cancel()
            with suppress(asyncio.CancelledError):
                await service._audio_context_task
            service._audio_context_task = None
        await service.cleanup()
        await service._client.close()


@pytest.mark.asyncio
async def test_cancel_does_not_flush_pending_text_or_wait_for_audio_drain():
    service = SpeachesLiveTTSService(
        api_key="test", base_url="http://localhost:8000/v1",
        settings=SpeachesTTSSettings(model="indic-vits-rasa-13", voice="HIN_F"),
    )
    synthesized = []
    emitted = []

    async def push(frame, direction=FrameDirection.DOWNSTREAM):
        emitted.append(frame)

    async def synthesize(text, context_id):
        synthesized.append(text)
        yield TTSAudioRawFrame(b"\x01\x00", 24000, 1, context_id=context_id)

    async def cancel_task(task, *args, **kwargs):
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    service.run_tts = synthesize
    service.push_frame = push
    service.cancel_task = cancel_task
    service._audio_contexts = {}
    service._audio_context_task = asyncio.create_task(asyncio.Event().wait())
    worker = service._audio_context_task
    try:
        async for _ in service._text_aggregator.aggregate("Discard this unfinished reply"):
            pass
        await asyncio.wait_for(service.process_frame(CancelFrame(), FrameDirection.DOWNSTREAM), timeout=0.2)
        assert worker.cancelled()
        assert service._audio_context_task is None
        assert synthesized == []
        assert len(emitted) == 1 and isinstance(emitted[0], CancelFrame)
    finally:
        if not worker.done():
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
        await service._client.close()
