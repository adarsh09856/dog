"""Organization-scoped caching for independent local Speaches PCM requests."""

import asyncio
from contextlib import aclosing, suppress

from openai import DefaultAsyncHttpxClient
from api.services.pipecat.tts_cache.models import SynthesisRequest
from api.services.pipecat.tts_cache.synthesis import cached_synthesis
from pipecat.frames.frames import ErrorFrame
from pipecat.services.speaches.tts import SpeachesTTSService
from api.services.pipecat.local_speech_aggregator import LocalSpeechAggregator
from pipecat.services.tts_service import TextAggregationMode


class SpeachesLiveTTSService(SpeachesTTSService):
    """Keep a synthesis context open while the CPU provider is working."""

    def __init__(self, **kwargs):
        kwargs.setdefault("http_client", DefaultAsyncHttpxClient(timeout=45.0))
        super().__init__(**kwargs)
        if self._text_aggregation_mode == TextAggregationMode.SENTENCE:
            # Keep short adjacent sentences in one synthesis stream. Each
            # independent Indus CPU request adds a perceptible pause and can
            # sound like a clipped turn; its response still streams PCM as it
            # synthesizes, so batching avoids request gaps without buffering
            # the complete audio before playback.
            # Start the first phrase promptly, then batch later phrases to
            # avoid repeated CPU synthesis gaps within a spoken reply.
            self._text_aggregator = LocalSpeechAggregator(
                min_characters=48,
                first_chunk_characters=24,
                first_clause_characters=14,
                first_phrase_characters=18,
            )
        # Avoid multiplying a stalled speech request through SDK retries.
        self._client.max_retries = 0

    async def run_tts(self, text: str, context_id: str):
        async def keep_context_open():
            while True:
                await asyncio.sleep(min(1.0, self._stop_frame_timeout_s / 2))
                if context_id in getattr(self, "_audio_contexts", {}):
                    self._refresh_audio_context(context_id)

        keepalive = asyncio.create_task(keep_context_open())
        try:
            async with aclosing(super().run_tts(text, context_id)) as frames:
                async for frame in frames:
                    yield frame
        finally:
            keepalive.cancel()
            with suppress(asyncio.CancelledError):
                await keepalive


class SpeachesCachingTTSService(SpeachesLiveTTSService):
    def __init__(self, *, speech_cache, organization_id: int, **kwargs):
        super().__init__(**kwargs)
        self._speech_cache = speech_cache
        self._organization_id = organization_id
        self._cache_endpoint = str(self._client.base_url)

    async def run_tts(self, text: str, context_id: str):
        payload = {
            "input": text,
            "model": self._settings.model,
            "voice": self._settings.voice,
            "response_format": "pcm",
            "speed": self._settings.speed,
            "instructions": self._settings.instructions,
        }
        request = SynthesisRequest.from_payload(
            organization_id=self._organization_id,
            provider="speaches",
            adapter_version=1,
            endpoint=self._cache_endpoint,
            credential=self._client.api_key,
            payload=payload,
            sample_rate=self.sample_rate,
            channels=1,
        )
        completed = False

        async def source():
            nonlocal completed
            failed = False
            async with aclosing(super(SpeachesCachingTTSService, self).run_tts(text, context_id)) as frames:
                async for frame in frames:
                    failed = failed or isinstance(frame, ErrorFrame)
                    yield frame
            completed = not failed

        frames = cached_synthesis(
            service=self, cache=self._speech_cache, request=request,
            context_id=context_id, source=source, completed=lambda: completed,
            chunk_size=self.chunk_size, text_length=len(text),
        )
        async with aclosing(frames):
            async for frame in frames:
                yield frame
