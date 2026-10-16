"""Bounded HTTP client for self-hosted Speaches transcription."""

import unicodedata
import io
import wave
from array import array
import sys

from openai import DefaultAsyncHttpxClient

from pipecat.services.speaches.stt import SpeachesSTTService


class BoundedSpeachesSTTService(SpeachesSTTService):
    """Keep a stalled local STT request from holding a voice turn for minutes."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("http_client", DefaultAsyncHttpxClient(timeout=45.0))
        super().__init__(*args, **kwargs)
        # The SDK otherwise retries timeouts, multiplying the per-request wait.
        self._client.max_retries = 0

    async def _transcribe(self, audio: bytes):
        """Drop Whisper's punctuation-only silence hallucinations before turn routing.

        Short, low-energy telephony frames can be decoded by Whisper as repeated
        danda/full-stop characters. Passing those into the LLM produces replies
        to silence. An empty transcription is intentionally ignored by Pipecat's
        BaseWhisperSTTService, so the caller gets no invented answer.
        """
        result = await super()._transcribe(_normalize_quiet_pcm16_wav(audio))
        text = (getattr(result, "text", None) or "").strip()
        if text and not any(
            unicodedata.category(char)[0] in {"L", "N"} for char in text
        ):
            return result.model_copy(update={"text": ""})
        return result


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
