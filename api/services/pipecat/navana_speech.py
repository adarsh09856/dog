"""Navana.ai Bodhi Speech Services for Pipecat (STT & TTS).

Implements real-time text-to-speech and speech-to-text integration with
Navana.ai Bodhi speech platform for Indian languages (docs.dev.navana.ai).
"""

import uuid
from collections.abc import AsyncGenerator
import aiohttp
from loguru import logger

from pipecat.frames.frames import (
    CancelFrame,
    ErrorFrame,
    Frame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService
from pipecat.utils.tracing.service_decorators import traced_tts


class NavanaTTSService(TTSService):
    """Navana.ai Bodhi Text-to-Speech service for Indian languages."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "bodhi-tts-v1",
        voice: str = "default_female",
        language: str = "hi",
        speed: float = 1.0,
        base_url: str = "https://tts.navana.ai",
        sample_rate: int = 24000,
        **kwargs,
    ):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._api_key = api_key or ""
        self._model = model
        self._voice = voice
        # Normalize language to 2-letter code if given BCP-47 (e.g. 'hi-IN' -> 'hi')
        self._language = language.split("-")[0].lower() if language else "hi"
        self._speed = speed
        self._base_url = base_url.rstrip("/")
        self._sample_rate = sample_rate

    def can_generate_metrics(self) -> bool:
        return True

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        logger.debug(f"[Navana TTS] Synthesizing: '{text[:40]}...' ({self._language}, {self._voice})")
        await self.start_tts_usage_metrics(text)
        yield TTSStartedFrame(context_id=context_id)

        # Official docs specify X-API-Key (capitalized) for TTS
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self._api_key,
        }
        # Supported output formats: '<sample_rate>:pcm16'
        rate = 8000 if self._sample_rate <= 8000 else (16000 if self._sample_rate <= 16000 else 24000)
        output_format = f"{rate}:pcm16"

        payload = {
            "text": text,
            "voice": self._voice,
            "lang": self._language,
            "speed": self._speed,
            "output_format": output_format,
        }

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self._base_url}/tts/bytes"
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.error(f"[Navana TTS] Error {resp.status}: {err_text}")
                        yield ErrorFrame(error=f"Navana TTS API error: {resp.status}")
                        yield TTSStoppedFrame(context_id=context_id)
                        return

                    # Audio is raw PCM (no WAV header) as configured via output_format
                    sample_rate_header = resp.headers.get("X-Sample-Rate")
                    actual_sample_rate = int(sample_rate_header) if sample_rate_header and sample_rate_header.isdigit() else rate

                    chunk_size = 4096
                    while True:
                        chunk = await resp.content.read(chunk_size)
                        if not chunk:
                            break
                        yield TTSAudioRawFrame(
                            audio=chunk,
                            sample_rate=actual_sample_rate,
                            num_channels=1,
                            context_id=context_id,
                        )
        except Exception as e:
            logger.error(f"[Navana TTS] Exception during synthesis: {e}")
            yield ErrorFrame(error=str(e))
        finally:
            await self.stop_tts_usage_metrics()
            yield TTSStoppedFrame(context_id=context_id)


class NavanaSTTService(STTService):
    """Navana.ai Bodhi Speech-to-Text service for Indian languages."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "hi-banking-v2-8khz",
        language: str = "hi-IN",
        base_url: str = "https://stt.navana.ai",
        sample_rate: int = 16000,
        **kwargs,
    ):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._api_key = api_key or ""
        self._model = model
        self._language = language
        self._base_url = base_url.rstrip("/")
        self._sample_rate = sample_rate

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        # Official docs specify X-Api-Key for STT, and required fields model, transaction_id (UUID), audio_file
        headers = {
            "X-Api-Key": self._api_key,
        }
        transaction_id = str(uuid.uuid4())
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self._base_url}/api/transcribe"
                data = aiohttp.FormData()
                data.add_field("audio_file", audio, filename="audio.wav", content_type="audio/wav")
                data.add_field("model", self._model)
                data.add_field("transaction_id", transaction_id)
                data.add_field("aux", "false")

                async with session.post(url, data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        text = result.get("text", "") or result.get("transcript", "")
                        if text:
                            yield TranscriptionFrame(text=text, user_id="caller", timestamp=0.0)
                    else:
                        err_text = await resp.text()
                        logger.warning(f"[Navana STT] API error {resp.status}: {err_text}")
        except Exception as e:
            logger.warning(f"[Navana STT] Recognition error: {e}")

