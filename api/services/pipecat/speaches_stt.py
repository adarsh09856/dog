"""Bounded HTTP client for self-hosted Speaches transcription."""

import unicodedata
import io
import wave
from array import array
import sys
import asyncio
import time
from dataclasses import replace

from openai import DefaultAsyncHttpxClient
from loguru import logger

from pipecat.services.speaches.stt import SpeachesSTTService
from pipecat.services.settings import STTSettings
from pipecat.frames.frames import ErrorFrame, InterimTranscriptionFrame, TranscriptionFrame


AUTO_LANGUAGE_MIN_CONFIDENCE = 0.65
AUTO_ENGLISH_MIN_CONFIDENCE = 0.50
# Languages exposed by the currently configured local VITS/Rasa voice inventory.
# STT may recognize more languages than the reply pipeline can currently speak.
LOCAL_REPLY_TTS_LANGUAGES = frozenset({
    "as", "bn", "brx", "doi", "en", "hi", "kn", "mai", "ml", "mr",
    "ne", "pa", "sa", "ta", "te",
})


def _is_auto_language(value: str | None) -> bool:
    return str(value or "").strip().casefold() in {
        "", "auto", "multi", "multilingual", "default", "unknown", "none",
    }


def _resolve_auto_language(
    detected: str | None,
    confidence: float | None,
    previous_stable: str | None,
) -> tuple[str | None, str]:
    """Keep short uncertain fragments from changing the call's reply language.

    Urdu is intentionally not an active Kodewaves speech language. Hindi and
    Urdu are acoustically close in Hindustani speech, so map that detector label
    to the Hindi decoder/voice route selected for this product.
    """
    code = str(detected or "").strip().lower().replace("_", "-").split("-", 1)[0]
    previous = str(previous_stable or "").strip().lower().replace("_", "-").split("-", 1)[0]
    if code == "ur":
        return "hi", "urdu_routed_to_hindi"
    if not code:
        return previous or None, "missing_detector_language"
    threshold = AUTO_ENGLISH_MIN_CONFIDENCE if code == "en" else AUTO_LANGUAGE_MIN_CONFIDENCE
    if confidence is not None and confidence < threshold and previous:
        return previous, "held_previous_low_confidence"
    return code, "detector"


def _trusted_tts_language(
    selected: str | None,
    confidence: float | None,
    previous_stable: str | None,
    route: str,
) -> str | None:
    """Avoid loading a different regional voice from a weak first-turn guess."""
    code = str(selected or "").strip().lower().replace("_", "-").split("-", 1)[0]
    previous = str(previous_stable or "").strip().lower().replace("_", "-").split("-", 1)[0]
    if route == "urdu_routed_to_hindi" and code == "hi":
        return "hi"
    if route in {"competitive_indian_english", "whisper_english_rescue"} and code == "en":
        return "en"
    if not code:
        return previous if previous in LOCAL_REPLY_TTS_LANGUAGES else None
    if code not in LOCAL_REPLY_TTS_LANGUAGES:
        # Preserve the speech transcript's detector result, but never route the
        # response to a voice that is absent from the configured TTS inventory.
        return previous if previous in LOCAL_REPLY_TTS_LANGUAGES else "hi"
    threshold = AUTO_ENGLISH_MIN_CONFIDENCE if code == "en" else AUTO_LANGUAGE_MIN_CONFIDENCE
    if confidence is None or confidence >= threshold:
        return code
    return previous if previous in LOCAL_REPLY_TTS_LANGUAGES else None


class BoundedSpeachesSTTService(SpeachesSTTService):
    """Keep a stalled local STT request from holding a voice turn for minutes."""

    recognition_timeout_seconds = 45.0

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("http_client", DefaultAsyncHttpxClient(timeout=self.recognition_timeout_seconds))
        super().__init__(*args, **kwargs)
        # The SDK otherwise retries timeouts, multiplying the per-request wait.
        self._client.max_retries = 0
        self.latest_detected_language: str | None = None
        # LLM language choice can use the best transcript guess, but TTS voice
        # routing must not treat a weak first-turn language guess as verified.
        self.latest_tts_language: str | None = None
        self.latest_detected_text: str | None = None
        self._stable_detected_language: str | None = None
        self._latest_language_confidence: float | None = None
        self._recognizing_segment = False

    async def select_caller_language(self, language: str) -> bool:
        """Honor a caller language choice without disabling automatic STT.

        In auto mode the detector must remain active for every utterance. In a
        fixed-language configuration, switch to a requested decoder only when
        that language is actually installed in the local recognizer.
        """
        if self._settings.model != "indicconformer-ctc-int8":
            return False
        requested = str(language or "").strip().lower().replace("_", "-")
        if requested in {"", "auto", "multi", "multilingual", "default", "unknown", "none"}:
            return False
        current = str(getattr(self._settings, "language", None) or "").strip().lower().replace("_", "-")
        if current in {"", "auto", "multi", "multilingual", "default", "unknown", "none"}:
            # Recognition remains per-utterance auto-detected. The caller's
            # response-language preference is handled independently by the LLM.
            return True
        from api.services.configuration.language_normalizer import LANGUAGE_NAME_TO_ISO

        code = LANGUAGE_NAME_TO_ISO.get(requested, requested.split("-", 1)[0])
        if code not in LANGUAGE_NAME_TO_ISO.values() and len(code) not in (2, 3):
            return False
        inventory = await asyncio.wait_for(self._client.models.list(), timeout=2.0)
        installed = {
            str(value).lower().replace("_", "-").split("-", 1)[0]
            for model in inventory.data
            if model.id == self._settings.model
            for value in (getattr(model, "languages", None) or [])
        }
        if code not in installed:
            return False
        await self._update_settings(STTSettings(language=code))
        return True

    @property
    def recognition_pending(self) -> bool:
        """Include queued speech, not only an accepted aggregator turn."""
        queue = getattr(self, "_segment_queue", None)
        return bool(
            self._recognizing_segment
            or getattr(self, "_user_speaking", False)
            or (queue is not None and not queue.empty())
        )

    async def _segment_task_handler(self):
        """Drain slow CPU recognition without answering an unfinished backlog.

        Queued VAD fragments belong to speech the caller has already delivered.
        Combine small pending WAVs into one bounded request and expose earlier
        recognized words as interim text until that backlog has been drained.
        """
        pending_text = []
        latest = None
        stopping = False
        carry = None
        while not stopping:
            audio = carry if carry is not None else await self._segment_queue.get()
            carry = None
            if audio is None:
                break
            while not self._segment_queue.empty():
                following = self._segment_queue.get_nowait()
                if following is None:
                    stopping = True
                    break
                combined = _join_wav_segments(audio, following)
                if combined is None:
                    carry = following
                    break
                audio = combined
            try:
                self._recognizing_segment = True
                async for frame in self.run_stt(audio):
                    if frame is None:
                        continue
                    if isinstance(frame, TranscriptionFrame):
                        pending_text.append(frame.text)
                        latest = frame
                    else:
                        if isinstance(frame, ErrorFrame):
                            # A later segment can fail after earlier recognized
                            # text was already shown as interim. Keep that
                            # accepted text so the caller's words still reach
                            # conversation history and the UI gets a final.
                            await self.push_error_frame(frame)
                        else:
                            await self.push_frame(frame)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Do not discard successful earlier segments from this
                # utterance when a subsequent HTTP recognition request fails.
                # The queue drain below will finalize that partial transcript.
                await self.push_error(f"{self}: transcription failed: {exc}", exception=exc)
            finally:
                self._recognizing_segment = False

            if latest is None:
                continue
            text = " ".join(pending_text)
            more_speech = (
                not stopping
                and (self._user_speaking or carry is not None or not self._segment_queue.empty())
            )
            if more_speech:
                await self.push_frame(InterimTranscriptionFrame(
                    text=text, user_id=latest.user_id, timestamp=latest.timestamp,
                    language=latest.language,
                ))
            else:
                await self.push_frame(replace(latest, text=text, finalized=True))
                pending_text.clear()
                latest = None
        if latest is not None:
            await self.push_frame(replace(latest, text=" ".join(pending_text), finalized=True))

    async def _transcribe(self, audio: bytes):
        """Drop Whisper's punctuation-only silence hallucinations before turn routing.

        Short, low-energy telephony frames can be decoded by Whisper as repeated
        danda/full-stop characters. Passing those into the LLM produces replies
        to silence. An empty transcription is intentionally ignored by Pipecat's
        BaseWhisperSTTService, so the caller gets no invented answer.
        """
        started_at = time.monotonic()
        normalized = _normalize_quiet_pcm16_wav(audio)
        # Whisper's verbose response carries the language detected for this
        # utterance. Keep it out of the saved transcript, but make it available
        # to the call's LLM so an English reply does not follow a Hindi greeting
        # merely because Hindi was selected for the assistant voice.
        settings = getattr(self, "_settings", None)
        detected_language = None
        language_confidence = None
        language_route = "configured"
        self.latest_tts_language = None
        if (
            settings is not None
            and _is_auto_language(settings.language)
            and (
                str(settings.model).startswith("Systran/faster-whisper-")
                or settings.model == "indicconformer-ctc-int8"
            )
        ):
            kwargs = {
                "file": ("audio.wav", normalized, "audio/wav"),
                "model": settings.model,
                "response_format": "verbose_json",
            }
            if settings.prompt is not None:
                kwargs["prompt"] = settings.prompt
            if settings.temperature is not None:
                kwargs["temperature"] = settings.temperature
            if settings.model == "indicconformer-ctc-int8" and self._stable_detected_language:
                kwargs["extra_body"] = {"fallback_language": self._stable_detected_language}
            result = await self._client.audio.transcriptions.create(**kwargs)
            response_extra = getattr(result, "model_extra", None) or {}
            raw_confidence = response_extra.get("language_confidence")
            try:
                language_confidence = float(raw_confidence) if raw_confidence is not None else None
            except (TypeError, ValueError):
                language_confidence = None
            selected = getattr(result, "language", None)
            detected_language = response_extra.get("detected_language") or selected
            if isinstance(detected_language, str):
                detected_language = detected_language.strip().lower()
            if settings.model == "indicconformer-ctc-int8":
                self.latest_detected_language = (
                    selected.strip().lower() if isinstance(selected, str) and selected.strip() else None
                )
                language_route = response_extra.get("language_route", "detector")
            else:
                self.latest_detected_language, language_route = _resolve_auto_language(
                    detected_language if isinstance(detected_language, str) else None,
                    language_confidence,
                    self._stable_detected_language,
                )
            self._latest_language_confidence = language_confidence
            if self.latest_detected_language and hasattr(result, "model_copy"):
                result = result.model_copy(update={"language": self.latest_detected_language})
        else:
            self.latest_detected_language = None
            self._latest_language_confidence = None
            result = await super()._transcribe(normalized)
        text = (getattr(result, "text", None) or "").strip()
        if text and not any(
            unicodedata.category(char)[0] in {"L", "N"} for char in text
        ):
            self.latest_detected_language = None
            self.latest_detected_text = None
            return result.model_copy(update={"text": ""})
        if not text:
            self.latest_detected_language = None
            self.latest_tts_language = None
        elif (
            self.latest_detected_language
            and settings is not None
            and _is_auto_language(settings.language)
            and (
                language_confidence is None
                or language_confidence >= (
                    AUTO_ENGLISH_MIN_CONFIDENCE
                    if detected_language == "en"
                    else AUTO_LANGUAGE_MIN_CONFIDENCE
                )
                or language_route in {"urdu_routed_to_hindi", "competitive_indian_english", "whisper_english_rescue"}
            )
        ):
            # Do not let empty or punctuation-only recognition overwrite the
            # prior language used as fallback for the next uncertain segment.
            self._stable_detected_language = self.latest_detected_language
        if text and (
            settings is not None
            and settings.model == "indicconformer-ctc-int8"
            and not _is_auto_language(settings.language)
        ):
            # This recognizer uses a language-specific decoder. Carry its
            # selected language to the per-turn reply/voice routing state;
            # this is the pinned recognition language, not auto detection.
            selected = str(settings.language or "").strip().lower().replace("_", "-").split("-", 1)[0]
            self.latest_detected_language = selected or None
            self.latest_tts_language = selected or None
        elif text and settings is not None and settings.model == "indicconformer-ctc-int8":
            self.latest_tts_language = _trusted_tts_language(
                self.latest_detected_language,
                self._latest_language_confidence,
                self._stable_detected_language,
                language_route,
            )
        elif text:
            # Providers that do not return calibrated detector confidence keep
            # their existing language routing behavior.
            self.latest_tts_language = self.latest_detected_language
        self.latest_detected_text = text or None
        if settings is not None and settings.model == "indicconformer-ctc-int8":
            mode = "auto" if _is_auto_language(settings.language) else "pinned"
            logger.info(
                "local_stt_result_trace model={} mode={} detected_language={} confidence={} route={} language={} tts_language={} text_chars={} duration_ms={}",
                settings.model,
                mode,
                detected_language or "unknown",
                round(language_confidence, 3) if language_confidence is not None else "unknown",
                language_route,
                self.latest_detected_language or "unknown",
                self.latest_tts_language or "script_or_voice_default",
                len(text),
                round((time.monotonic() - started_at) * 1000),
            )
        return result


def _join_wav_segments(first: bytes, second: bytes, max_seconds: float = 20) -> bytes | None:
    """Join matching PCM segments; preserve queue order when formats differ."""
    try:
        parts = []
        params = None
        frames = 0
        for audio in (first, second):
            with wave.open(io.BytesIO(audio), "rb") as source:
                current = source.getparams()
                signature = (current.nchannels, current.sampwidth, current.framerate, current.comptype)
                if params is not None and signature != params:
                    return None
                if current.comptype != "NONE" or current.sampwidth != 2:
                    return None
                params = signature
                frames += current.nframes
                if frames / current.framerate > max_seconds:
                    return None
                data = source.readframes(current.nframes)
                if len(data) != current.nframes * current.nchannels * current.sampwidth:
                    return None
                parts.append(data)
        output = io.BytesIO()
        with wave.open(output, "wb") as target:
            target.setnchannels(params[0])
            target.setsampwidth(params[1])
            target.setframerate(params[2])
            target.writeframes(b"".join(parts))
        return output.getvalue()
    except (wave.Error, EOFError, ValueError):
        return None


def _normalize_quiet_pcm16_wav(audio: bytes) -> bytes:
    """Raise quiet VAD-bounded speech without clipping or amplifying silence.

    WebRTC microphone levels vary greatly between browsers and headsets. A
    quiet but valid utterance can make Whisper spend seconds hallucinating
    repetitive text. The peak limit keeps this adjustment conservative.
    """
    try:
        with wave.open(io.BytesIO(audio), "rb") as source:
            if source.getsampwidth() != 2 or source.getnchannels() != 1:
                return audio
            params = source.getparams()
            frames = source.readframes(source.getnframes())
        samples = array("h")
        samples.frombytes(frames)
        if sys.byteorder != "little":
            samples.byteswap()
        if not samples:
            return audio
        rms = (sum(sample * sample for sample in samples) / len(samples)) ** 0.5
        peak = max(abs(sample) for sample in samples)
        if rms < 150 or peak == 0 or rms >= 3500:
            return audio
        gain = min(3500 / rms, 29490 / peak, 4.0)
        if gain <= 1.1:
            return audio
        adjusted = array("h", (round(sample * gain) for sample in samples))
        if sys.byteorder != "little":
            adjusted.byteswap()
        output = io.BytesIO()
        with wave.open(output, "wb") as target:
            target.setparams(params)
            target.writeframes(adjusted.tobytes())
        return output.getvalue()
    except (EOFError, ValueError, wave.Error):
        return audio
