from collections import Counter
import asyncio

import pytest
from pipecat.frames.frames import ErrorFrame, TTSAudioRawFrame
from pipecat.services.speaches.tts import SpeachesTTSService, SpeachesTTSSettings

from api.services.pipecat.speaches_tts import SpeachesCachingTTSService, SpeachesLiveTTSService
from api.services.pipecat.tts_cache.cache import SpeechCache
from api.services.pipecat.tts_cache.models import CachePolicy
from api.tests.test_tts_cache import MemoryBackend


@pytest.mark.asyncio
async def test_speaches_replays_selected_voice_and_isolates_voice_speed_and_org(monkeypatch):
    calls = Counter()

    async def synthesize(self, text, context_id):
        calls[self._settings.voice] += 1
        yield TTSAudioRawFrame(b'\x01\x02' * 128, 24000, 1, context_id=context_id)

    monkeypatch.setattr(SpeachesTTSService, 'run_tts', synthesize)
    cache = SpeechCache(MemoryBackend(), CachePolicy())

    def service(org=1, voice='hf_alpha', speed=1.0):
        instance = SpeachesCachingTTSService(
            speech_cache=cache, organization_id=org, api_key='local',
            base_url='http://localhost:8000/v1', sample_rate=24000,
            settings=SpeachesTTSSettings(model='kokoro', voice=voice, speed=speed))
        instance._sample_rate = 24000
        return instance

    first = service()
    for index in range(4):
        frames = [frame async for frame in first.run_tts('नमस्ते', f'context-{index}')]
        assert b''.join(frame.audio for frame in frames) == b'\x01\x02' * 128
        assert all(frame.context_id == f'context-{index}' for frame in frames)
    assert calls['hf_alpha'] == 3  # Existing cache promotes three validated samples.
    for variant in (service(org=2), service(voice='hf_beta'), service(speed=1.1)):
        assert [frame async for frame in variant.run_tts('नमस्ते', 'new')]
    assert calls == {'hf_alpha': 5, 'hf_beta': 1}


@pytest.mark.asyncio
async def test_failed_speaches_audio_is_never_cached(monkeypatch):
    calls = []

    async def fail(self, text, context_id):
        calls.append(text)
        yield ErrorFrame(error='synthetic failure')

    monkeypatch.setattr(SpeachesTTSService, 'run_tts', fail)
    service = SpeachesCachingTTSService(
        speech_cache=SpeechCache(MemoryBackend(), CachePolicy()), organization_id=1,
        api_key='local', base_url='http://localhost:8000/v1', sample_rate=24000,
        settings=SpeachesTTSSettings(model='kokoro', voice='hf_alpha'))
    service._sample_rate = 24000
    for _ in range(4):
        assert isinstance([frame async for frame in service.run_tts('Hello', 'c')][0], ErrorFrame)
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_slow_cpu_synthesis_keeps_context_open_until_audio_arrives(monkeypatch):
    async def slow(self, text, context_id):
        await asyncio.sleep(0.04)
        yield TTSAudioRawFrame(b'\x01\x02' * 128, 24000, 1, context_id=context_id)
    monkeypatch.setattr(SpeachesTTSService, 'run_tts', slow)
    service = SpeachesLiveTTSService(api_key='local', stop_frame_timeout_s=0.01,
        settings=SpeachesTTSSettings(model='kokoro', voice='hf_alpha'))
    assert service._client.max_retries == 0
    assert service._client.timeout.read == 45.0
    service._audio_contexts = {'c': asyncio.Queue()}
    frames = [frame async for frame in service.run_tts('नमस्ते', 'c')]
    assert len(frames) == 1
    assert service._audio_contexts['c'].qsize() > 0
    count = service._audio_contexts['c'].qsize()
    await asyncio.sleep(0.03)
    assert service._audio_contexts['c'].qsize() == count  # No leaked keepalive task.
