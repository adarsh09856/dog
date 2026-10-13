"""Speaches STT Service — uses the OpenAI-compatible /v1/audio/transcriptions endpoint."""

from dataclasses import dataclass

from pipecat.services.openai.stt import OpenAISTTService, OpenAISTTSettings
from pipecat.services.whisper.base_stt import Transcription


@dataclass
class SpeachesSTTSettings(OpenAISTTSettings):
    """Settings for Speaches STT service."""

    pass


class SpeachesSTTService(OpenAISTTService):
    """Speaches STT service using the OpenAI-compatible transcription endpoint.

    Speaches exposes ``/v1/audio/transcriptions`` with an OpenAI-compatible
    multipart request format, so we can reuse the segmented HTTP STT adapter
    instead of a custom websocket protocol.
    """

    Settings = SpeachesSTTSettings

    def __init__(
        self,
        *,
        api_key: str = "none",
        base_url: str = "http://localhost:8000/v1",
        settings: SpeachesSTTSettings | None = None,
        **kwargs,
    ):
        """Initialize the Speaches STT service.

        Args:
            api_key: API key for authentication.
            base_url: Base URL for the Speaches API.
            settings: Optional STT settings.
            **kwargs: Additional arguments passed to parent.
        """
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            settings=settings,
            **kwargs,
        )

    async def _transcribe(self, audio: bytes) -> Transcription:
        """Pass an explicit language, or omit it for Speaches auto detection."""
        kwargs = {
            "file": ("audio.wav", audio, "audio/wav"),
            "model": self._settings.model,
        }
        if self._settings.language:
            kwargs["language"] = str(self._settings.language).split("-")[0].lower()
        if self._settings.prompt is not None:
            kwargs["prompt"] = self._settings.prompt
        if self._settings.temperature is not None:
            kwargs["temperature"] = self._settings.temperature
        return await self._client.audio.transcriptions.create(**kwargs)
