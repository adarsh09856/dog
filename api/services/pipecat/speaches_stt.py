"""Bounded HTTP client for self-hosted Speaches transcription."""

import unicodedata
import io
import wave
from array import array
import sys
import asyncio
from dataclasses import replace

from openai import DefaultAsyncHttpxClient

from pipecat.services.speaches.stt import SpeachesSTTService
from pipecat.frames.frames import ErrorFrame, InterimTranscriptionFrame, TranscriptionFrame


class BoundedSpeachesSTTService(SpeachesSTTService):
    """Keep a stalled local STT request from holding a voice turn for minutes."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("http_client", DefaultAsyncHttpxClient(timeout=45.0))
        super().__init__(*args, **kwargs)
        # The SDK otherwise retries timeouts, multiplying the per-request wait.
        self._client.max_retries = 0
        self.latest_detected_language: str | None = None
        self.latest_detected_text: str | None = None

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
                async for frame in self.run_stt(audio):
                    if frame is None:
                        continue
                    if isinstance(frame, TranscriptionFrame):
                        pending_text.append(frame.text)
                        latest = frame
                    else:
                        if isinstance(frame, ErrorFrame):
                            pending_text.clear()
                            latest = None
                            await self.push_error_frame(frame)
                        else:
                            await self.push_frame(frame)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                pending_text.clear()
                latest = None
                await self.push_error(f"{self}: transcription failed: {exc}", exception=exc)

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
                await self.push_frame(replace(latest, text=text))
                pending_text.clear()
                latest = None
        if latest is not None:
            await self.push_frame(replace(latest, text=" ".join(pending_text)))

    async def _transcribe(self, audio: bytes):
        """Drop Whisper's punctuation-only silence hallucinations before turn routing.

        Short, low-energy telephony frames can be decoded by Whisper as repeated
        danda/full-stop characters. Passing those into the LLM produces replies
        to silence. An empty transcription is intentionally ignored by Pipecat's
        BaseWhisperSTTService, so the caller gets no invented answer.
        """
        normalized = _normalize_quiet_pcm16_wav(audio)
        # Whisper's verbose response carries the language detected for this
        # utterance. Keep it out of the saved transcript, but make it available
        # to the call's LLM so an English reply does not follow a Hindi greeting
        # merely because Hindi was selected for the assistant voice.
        settings = getattr(self, "_settings", None)
        if (
            settings is not None
            and str(settings.model).startswith("Systran/faster-whisper-")
            and not settings.language
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
            result = await self._client.audio.transcriptions.create(**kwargs)
            detected = getattr(result, "language", None)
            self.latest_detected_language = (
                detected.strip().lower() if isinstance(detected, str) and detected.strip() else None
            )
        else:
            self.latest_detected_language = None
            result = await super()._transcribe(normalized)
        text = (getattr(result, "text", None) or "").strip()
        if text and not any(
            unicodedata.category(char)[0] in {"L", "N"} for char in text
        ):
            self.latest_detected_text = None
            return result.model_copy(update={"text": ""})
        self.latest_detected_text = text or None
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
