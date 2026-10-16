"""Bounded HTTP client for self-hosted Speaches transcription."""

import unicodedata

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
        result = await super()._transcribe(audio)
        text = (getattr(result, "text", None) or "").strip()
        if text and not any(
            unicodedata.category(char)[0] in {"L", "N"} for char in text
        ):
            return result.model_copy(update={"text": ""})
        return result
