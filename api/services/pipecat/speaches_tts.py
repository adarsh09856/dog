"""Organization-scoped caching for independent local Speaches PCM requests."""

from contextlib import aclosing

from api.services.pipecat.tts_cache.models import SynthesisRequest
from api.services.pipecat.tts_cache.synthesis import cached_synthesis
from pipecat.frames.frames import ErrorFrame
from pipecat.services.speaches.tts import SpeachesTTSService


class SpeachesCachingTTSService(SpeachesTTSService):
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
