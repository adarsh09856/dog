import asyncio
import io
import wave
from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import ErrorFrame, InterimTranscriptionFrame, TranscriptionFrame
from api.services.pipecat.speaches_stt import BoundedSpeachesSTTService, _join_wav_segments


def wav(value, seconds=0.1, rate=16000):
    out = io.BytesIO()
    with wave.open(out, 'wb') as writer:
        writer.setnchannels(1); writer.setsampwidth(2); writer.setframerate(rate)
        writer.writeframes(value.to_bytes(2, 'little') * int(seconds * rate))
    return out.getvalue()


def service():
    instance = object.__new__(BoundedSpeachesSTTService)
    instance._segment_queue = asyncio.Queue()
    instance._user_speaking = False
    instance.push_error = AsyncMock()
    return instance


def test_wav_batch_preserves_pcm_order_and_has_a_duration_limit():
    joined = _join_wav_segments(wav(1), wav(2))
    with wave.open(io.BytesIO(joined), 'rb') as reader:
        assert reader.getnframes() == 3200
        assert reader.readframes(3200) == b'\x01\x00' * 1600 + b'\x02\x00' * 1600
    assert _join_wav_segments(wav(1), wav(2, rate=8000)) is None
    assert _join_wav_segments(wav(1, seconds=19), wav(2, seconds=2)) is None
    assert _join_wav_segments(b'broken', wav(1)) is None


@pytest.mark.asyncio
async def test_slow_stt_batches_backlog_and_commits_one_complete_user_turn():
    instance = service()
    started, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
    requests, emitted = [], []

    async def recognize(audio):
        requests.append(audio)
        if len(requests) == 1:
            started.set()
            await release.wait()
            text = 'मेरा नाम आदर्श है।'
        else:
            text = 'Can you help with my account?'
        yield TranscriptionFrame(text, 'caller', 'test-time')

    async def push(frame):
        emitted.append(frame)
        if isinstance(frame, TranscriptionFrame): finished.set()
    instance.run_stt = recognize
    instance.push_frame = push
    await instance._segment_queue.put(wav(1))
    task = asyncio.create_task(instance._segment_task_handler())
    try:
        await asyncio.wait_for(started.wait(), 1)
        await instance._segment_queue.put(wav(2))
        await instance._segment_queue.put(wav(3))
        release.set()
        await asyncio.wait_for(finished.wait(), 1)
        await instance._segment_queue.put(None)
        await asyncio.wait_for(task, 1)
    finally:
        task.cancel()
    assert len(requests) == 2
    assert isinstance(emitted[0], InterimTranscriptionFrame)
    assert emitted[0].text == 'मेरा नाम आदर्श है।'
    assert [frame.text for frame in emitted if isinstance(frame, TranscriptionFrame)] == [
        'मेरा नाम आदर्श है। Can you help with my account?'
    ]
    assert emitted[-1].finalized is True
    with wave.open(io.BytesIO(requests[1]), 'rb') as reader:
        assert reader.getnframes() == 3200


@pytest.mark.asyncio
async def test_shutdown_drains_recognized_text_without_duplicate_final():
    instance = service()
    emitted = []
    async def recognize(audio): yield TranscriptionFrame('Complete answer', '', '')
    async def push(frame): emitted.append(frame)
    instance.run_stt = recognize; instance.push_frame = push; instance.push_error_frame = push
    await instance._segment_queue.put(wav(1)); await instance._segment_queue.put(None)
    await asyncio.wait_for(instance._segment_task_handler(), 1)
    assert len(emitted) == 1
    assert isinstance(emitted[0], TranscriptionFrame)
    assert emitted[0].finalized is True


@pytest.mark.asyncio
async def test_failed_recognition_never_commits_a_partial_earlier_request():
    instance = service()
    started, release = asyncio.Event(), asyncio.Event()
    emitted, count = [], 0
    async def recognize(audio):
        nonlocal count
        count += 1
        if count == 1:
            started.set(); await release.wait()
            yield TranscriptionFrame('Incomplete', '', '')
        else: yield ErrorFrame(error='Recognition failed')
    async def push(frame): emitted.append(frame)
    instance.run_stt = recognize; instance.push_frame = push; instance.push_error_frame = push
    await instance._segment_queue.put(wav(1))
    task = asyncio.create_task(instance._segment_task_handler())
    await asyncio.wait_for(started.wait(), 1)
    await instance._segment_queue.put(wav(2)); await instance._segment_queue.put(None)
    release.set(); await asyncio.wait_for(task, 1)
    assert isinstance(emitted[0], InterimTranscriptionFrame)
    assert isinstance(emitted[1], ErrorFrame)
    assert not any(isinstance(frame, TranscriptionFrame) for frame in emitted)
