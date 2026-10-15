"""Bounded HTTP client for self-hosted Speaches transcription."""

from openai import DefaultAsyncHttpxClient
from pipecat.services.speaches.stt import SpeachesSTTService


class BoundedSpeachesSTTService(SpeachesSTTService):
    """Keep a stalled local STT request from holding a voice turn for minutes."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("http_client", DefaultAsyncHttpxClient(timeout=45.0))
        super().__init__(*args, **kwargs)
        # The SDK otherwise retries timeouts, multiplying the per-request wait.
        self._client.max_retries = 0
