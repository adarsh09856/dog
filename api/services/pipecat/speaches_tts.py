"""Organization-scoped caching for independent local Speaches PCM requests."""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import aclosing, suppress
from dataclasses import dataclass

from openai import BadRequestError, DefaultAsyncHttpxClient

from api.services.configuration.language_normalizer import normalize_language_code
from api.services.pipecat.local_speech_aggregator import LocalSpeechAggregator
from api.services.pipecat.tts_cache.models import SynthesisRequest
from api.services.pipecat.tts_cache.synthesis import cached_synthesis
from pipecat.frames.frames import CancelFrame, ErrorFrame, Frame, InterruptionFrame, TTSAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.speaches.tts import SpeachesTTSService
from pipecat.services.tts_service import TextAggregationMode
from pipecat.utils.tracing.service_decorators import traced_tts


@dataclass
class _PrefetchedSpeech:
    """One ordered local-TTS request that can synthesize ahead of playback."""

    context_id: str
    frames: asyncio.Queue[Frame | None]


class SpeachesLiveTTSService(SpeachesTTSService):
    """Keep a synthesis context open while the CPU provider is working."""

    def __init__(self, *, speech_language: str | None = None, **kwargs):
        kwargs.setdefault("http_client", DefaultAsyncHttpxClient(timeout=45.0))
        super().__init__(**kwargs)
        self._speech_language = speech_language
        self._speech_turn_open = False
        self._turn_speech_language = None
        if self._text_aggregation_mode == TextAggregationMode.SENTENCE:
            # Keep short adjacent sentences in one synthesis stream. Each
            # independent CPU request adds a perceptible pause and can
            # sound like a clipped turn; its response still streams PCM as it
            # synthesizes, so batching avoids request gaps without buffering
            # the complete audio before playback.
            # Do not start CPU synthesis with a tiny two-or-three-word
            # fragment. It often finishes before the LLM produces enough text
            # for the next request, creating several seconds of dead air. A
            # 20-character first phrase is enough audible material to overlap
            # normal local generation without waiting for a full sentence.
            # Following phrases use a small batch too: prefetching keeps their
            # requests ready while the prior phrase plays, rather than making
            # the caller wait for a 48-character sentence boundary.
            self._text_aggregator = LocalSpeechAggregator(
                min_characters=24,
                first_chunk_characters=20,
                first_clause_characters=20,
                first_phrase_characters=20,
                streaming_phrase_characters=24,
            )
        # Avoid multiplying a stalled speech request through SDK retries.
        self._client.max_retries = 0
        # The stock HTTP TTS path consumes each synthesis generator before it
        # accepts the next LLM phrase. On a CPU VITS server that creates a
        # silent gap after every short phrase. Keep HTTP fetches concurrent,
        # while a single ordered dispatcher still sends PCM to playback in the
        # original text order.
        self._prefetched_speech: list[_PrefetchedSpeech] = []
        self._prefetch_workers: set[asyncio.Task] = set()
        self._prefetch_dispatcher: asyncio.Task | None = None
        self._prefetch_changed = asyncio.Event()
        self._prefetch_closing = False
        self._prefetch_generation = 0
        self._turn_keepalive: asyncio.Task | None = None

    async def _stop_turn_keepalive(self):
        task, self._turn_keepalive = self._turn_keepalive, None
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def cleanup(self):
        await self._cancel_prefetch()
        await super().cleanup()

    async def cancel(self, frame: CancelFrame):
        await self._cancel_prefetch()
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
            async with self._client.audio.speech.with_streaming_response.create(**params) as response:
                if response.status_code != 200:
                    yield ErrorFrame(error=f"Local speech returned HTTP {response.status_code}")
                    return
                await self.start_tts_usage_metrics(text)
                async for chunk in response.iter_bytes(self.chunk_size):
                    if chunk:
                        await self.stop_ttfb_metrics()
                        yield TTSAudioRawFrame(chunk, self.sample_rate, 1, context_id=context_id)
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
        self._prefetch_generation += 1
        self._prefetched_speech = []
        self._prefetch_workers = set()
        self._prefetch_dispatcher = None
        self._prefetch_changed = asyncio.Event()
        self._prefetch_closing = False
        await super().on_turn_context_created(context_id)
        async def keep_turn_open():
            while True:
                await asyncio.sleep(min(1.0, self._stop_frame_timeout_s / 2))
                if self.audio_context_available(context_id):
                    self._refresh_audio_context(context_id)
        # LLM text may take longer than the audio-context timeout between
        # phrases. Keep it alive until all prefetched synthesis has drained.
        self._turn_keepalive = asyncio.create_task(keep_turn_open())

    async def _fetch_speech(
        self,
        speech: _PrefetchedSpeech,
        generator: AsyncGenerator[Frame | None, None],
        generation: int,
    ):
        try:
            async for frame in generator:
                if generation != self._prefetch_generation:
                    return
                if frame:
                    await speech.frames.put(frame)
        except Exception as exc:  # noqa: BLE001 - forward task failures through the pipeline error channel
            if generation == self._prefetch_generation:
                await speech.frames.put(ErrorFrame(
                    error="Local speech synthesis failed",
                    processor=self,
                    exception=exc,
                ))
        finally:
            await speech.frames.put(None)

    async def _dispatch_prefetched_speech(self, generation: int):
        index = 0
        while generation == self._prefetch_generation:
            if index >= len(self._prefetched_speech):
                if self._prefetch_closing:
                    return
                await self._prefetch_changed.wait()
                self._prefetch_changed.clear()
                continue
            speech = self._prefetched_speech[index]
            index += 1
            while generation == self._prefetch_generation:
                frame = await speech.frames.get()
                if frame is None:
                    break
                await self.append_to_audio_context(speech.context_id, frame)

    async def tts_process_generator(
        self, context_id: str, generator: AsyncGenerator[Frame | None, None]
    ):
        """Fetch following phrases while the earlier phrase is being played."""
        generation = self._prefetch_generation
        speech = _PrefetchedSpeech(context_id=context_id, frames=asyncio.Queue())
        self._prefetched_speech.append(speech)
        worker = asyncio.create_task(self._fetch_speech(speech, generator, generation))
        self._prefetch_workers.add(worker)
        worker.add_done_callback(self._prefetch_workers.discard)
        if self._prefetch_dispatcher is None or self._prefetch_dispatcher.done():
            self._prefetch_dispatcher = asyncio.create_task(
                self._dispatch_prefetched_speech(generation)
            )
        self._prefetch_changed.set()
        # The background dispatcher owns the HTTP generators. Do not mark the
        # shared turn context synchronous until all generated PCM has arrived.
        self._is_yielding_frames_synchronously = False

    async def on_turn_context_completed(self):
        self._prefetch_closing = True
        self._prefetch_changed.set()
        dispatcher = self._prefetch_dispatcher
        if dispatcher:
            # Cancellation here belongs to the frame-processing task (barge-in).
            # Swallowing it prevents the framework from stopping the old turn.
            await dispatcher
        # At this point every queued HTTP generator has finished and the base
        # class can safely close the shared audio context behind its PCM.
        self._is_yielding_frames_synchronously = True
        await super().on_turn_context_completed()
        self._speech_turn_open = False
        await self._stop_turn_keepalive()

    async def _cancel_prefetch(self):
        """Stop request generators on disconnect as well as caller interruption."""
        await self._stop_turn_keepalive()
        self._prefetch_generation += 1
        tasks = [*self._prefetch_workers]
        if self._prefetch_dispatcher:
            tasks.append(self._prefetch_dispatcher)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._prefetched_speech = []
        self._prefetch_workers = set()
        self._prefetch_dispatcher = None
        self._speech_turn_open = False

    async def _handle_interruption(self, frame: InterruptionFrame, direction: FrameDirection):
        await self._cancel_prefetch()
        await super()._handle_interruption(frame, direction)


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
        if self._settings.model == "indic-vits-rasa-13":
            payload["language"] = self._request_speech_language()
            # The combined endpoint keeps stable public voice IDs while its
            # backend changes. Do not replay former Piper/Melo audio as Inaya,
            # or Inaya audio after an operator rolls back to the regional route.
            payload["routing_profile"] = (
                "indus-inaya-v1" if os.environ.get("INDUS_COMBINED_ENDPOINT") else "regional-v4"
            )
        request = SynthesisRequest.from_payload(
            organization_id=self._organization_id,
            provider="speaches",
            # Unified voice routing must not reuse former Rasa-only audio.
            adapter_version=4 if self._settings.model == "indic-vits-rasa-13" else 1,
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
