"""Organization-scoped caching for independent local Speaches PCM requests."""

import asyncio
import os
from contextlib import aclosing, suppress

from openai import BadRequestError, DefaultAsyncHttpxClient

from api.services.configuration.language_normalizer import normalize_language_code
from api.services.pipecat.local_speech_aggregator import LocalSpeechAggregator
from api.services.pipecat.tts_cache.models import SynthesisRequest
from api.services.pipecat.tts_cache.synthesis import cached_synthesis
from pipecat.frames.frames import CancelFrame, ErrorFrame, InterruptionFrame, TTSAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.speaches.tts import SpeachesTTSService
from pipecat.services.tts_service import TextAggregationMode
from pipecat.utils.tracing.service_decorators import traced_tts


class SpeachesLiveTTSService(SpeachesTTSService):
    """Keep a synthesis context open while the CPU provider is working."""

    @property
    def chunk_size(self) -> int:
        # The local gateway generates faster than playback. A 200 ms initial
        # buffer releases speech sooner without requesting one HTTP frame per
        # tiny model callback.
        # Pipecat initializes sample_rate when StartFrame arrives. Before that,
        # use the configured output rate so this property never yields zero.
        rate = self.sample_rate or self._init_sample_rate or 24000
        return int(rate * 0.2 * 2)

    def __init__(self, *, speech_language: str | None = None, **kwargs):
        kwargs.setdefault("http_client", DefaultAsyncHttpxClient(timeout=45.0))
        super().__init__(**kwargs)
        self._speech_language = speech_language
        self._speech_turn_open = False
        self._turn_speech_language = None
        if self._text_aggregation_mode == TextAggregationMode.SENTENCE:
            # Start on a completed short sentence rather than waiting for the
            # full model answer. Larger fixed thresholds delay first audio;
            # downstream PCM/history ordering is handled by the base service.
            self._text_aggregator = LocalSpeechAggregator(
                min_characters=24,
                first_chunk_characters=12,
                first_clause_characters=36,
                first_phrase_characters=None,
                # Keep each later Inaya request long enough for coherent
                # prosody, but release it before the full sentence ends so the
                # next synthesis can overlap the current audio playback.
                streaming_phrase_characters=64,
            )
        # Avoid multiplying a stalled speech request through SDK retries.
        self._client.max_retries = 0
        # HTTP synthesis and downstream playback already run independently in
        # Pipecat. Consume each generator before its TTSTextFrame is queued so
        # history never treats not-yet-generated audio as spoken. The endpoint
        # is single-worker, so background HTTP prefetch cannot parallelize it.
        self._turn_keepalive: asyncio.Task | None = None

    async def _stop_turn_keepalive(self):
        task, self._turn_keepalive = self._turn_keepalive, None
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def cleanup(self):
        await self._stop_turn_keepalive()
        await super().cleanup()

    async def cancel(self, frame: CancelFrame):
        await self._stop_turn_keepalive()
        await super().cancel(frame)

    def _resolve_speech_language(self):
        source = getattr(self, "_caller_language_source", None)
        for value in (
            getattr(source, "latest_detected_language", None),
            getattr(getattr(source, "_settings", None), "language", None),
            self._speech_language,
        ):
            if value is None:
                continue
            code = normalize_language_code(getattr(value, "value", value))
            if code not in {"", "auto", "multi", "multilingual", "unknown", "default", "none"}:
                return code
        return None

    def _request_speech_language(self):
        return self._turn_speech_language if self._speech_turn_open else self._resolve_speech_language()

    @traced_tts
    async def _run_combined_tts(self, text: str, context_id: str, language: str | None):
        # Headers are request-local: prefetched requests must never mutate a
        # shared client while a later utterance changes STT's language state.
        params = {
            "input": text, "model": self._settings.model,
            "voice": self._settings.voice, "response_format": "pcm",
        }
        if language:
            params["extra_headers"] = {"X-Kodewaves-Speech-Language": language}
        if self._settings.instructions:
            params["instructions"] = self._settings.instructions
        if self._settings.speed:
            params["speed"] = self._settings.speed
        try:
            for attempt in range(2):
                received_audio = False
                async with self._client.audio.speech.with_streaming_response.create(**params) as response:
                    if response.status_code != 200:
                        yield ErrorFrame(error=f"Local speech returned HTTP {response.status_code}")
                        return
                    async for chunk in response.iter_bytes(self.chunk_size):
                        if chunk:
                            if not received_audio:
                                await self.start_tts_usage_metrics(text)
                                received_audio = True
                            await self.stop_ttfb_metrics()
                            yield TTSAudioRawFrame(chunk, self.sample_rate, 1, context_id=context_id)
                if received_audio:
                    return
                if attempt:
                    yield ErrorFrame(error="Local speech returned no audio after retry")
        except BadRequestError as exc:
            yield ErrorFrame(error=f"Local speech request was rejected: {exc}")

    async def run_tts(self, text: str, context_id: str):
        async def keep_context_open():
            while True:
                await asyncio.sleep(min(1.0, self._stop_frame_timeout_s / 2))
                if context_id in getattr(self, "_audio_contexts", {}):
                    self._refresh_audio_context(context_id)

        keepalive = asyncio.create_task(keep_context_open())
        try:
            generator = (
                self._run_combined_tts(text, context_id, self._request_speech_language())
                if self._settings.model == "indic-vits-rasa-13"
                else super().run_tts(text, context_id)
            )
            async with aclosing(generator) as frames:
                async for frame in frames:
                    yield frame
        finally:
            keepalive.cancel()
            with suppress(asyncio.CancelledError):
                await keepalive

    async def on_turn_context_created(self, context_id: str):
        await self._stop_turn_keepalive()
        self._turn_speech_language = self._resolve_speech_language()
        self._speech_turn_open = True
        await super().on_turn_context_created(context_id)
        async def keep_turn_open():
            while True:
                await asyncio.sleep(min(1.0, self._stop_frame_timeout_s / 2))
                if self.audio_context_available(context_id):
                    self._refresh_audio_context(context_id)
        # LLM text may take longer than the audio-context timeout between
        # phrases. Keep it alive until all prefetched synthesis has drained.
        self._turn_keepalive = asyncio.create_task(keep_turn_open())

    async def on_turn_context_completed(self):
        try:
            await super().on_turn_context_completed()
        finally:
            self._speech_turn_open = False
            await self._stop_turn_keepalive()

    async def _handle_interruption(self, frame: InterruptionFrame, direction: FrameDirection):
        await self._stop_turn_keepalive()
        self._speech_turn_open = False
        await super()._handle_interruption(frame, direction)


class SpeachesCachingTTSService(SpeachesLiveTTSService):
    def __init__(self, *, speech_cache, organization_id: int, **kwargs):
        super().__init__(**kwargs)
        self._speech_cache = speech_cache
        self._organization_id = organization_id
        self._cache_endpoint = str(self._client.base_url)

    async def run_tts(self, text: str, context_id: str):
        combined_model = self._settings.model == "indic-vits-rasa-13"
        indus_profile = combined_model and bool(os.environ.get("INDUS_COMBINED_ENDPOINT"))
        payload = {
            "input": text,
            "model": self._settings.model,
            "voice": self._settings.voice,
            "response_format": "pcm",
            "speed": self._settings.speed,
            "instructions": self._settings.instructions,
        }
        if combined_model:
            payload["language"] = self._request_speech_language()
            # The combined endpoint keeps stable public voice IDs while its
            # backend changes. Do not replay former Piper/Melo audio as Inaya,
            # or Inaya audio after an operator rolls back to the regional route.
            payload["routing_profile"] = (
                "indus-inaya-edge-v2" if indus_profile else "regional-v4"
            )
        request = SynthesisRequest.from_payload(
            organization_id=self._organization_id,
            provider="speaches",
            # Unified voice routing must not reuse former Rasa-only audio.
            adapter_version=5 if indus_profile else 4 if combined_model else 1,
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
