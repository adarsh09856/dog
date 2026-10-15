"""Google Gemini TTS for Pipecat, including streamed Gemini 3.8 output."""

import asyncio
from collections.abc import AsyncGenerator
import base64
import io
import json
import re
import wave

import aiohttp
from loguru import logger

from api.services.catalog.gemini_voices import supports_gemini_voice
from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.services.tts_service import TTSService
from pipecat.services.settings import TTSSettings
from pipecat.utils.tracing.service_decorators import traced_tts


class GeminiTTSService(TTSService):
    """Use an organization-authorized Google AI Studio key for Gemini TTS."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gemini-3.8-flash-lite-tts",
        voice: str = "Puck",
        sample_rate: int = 24000,
        **kwargs,
    ):
        resolved_model = model if (model and "tts" in model.lower()) else "gemini-3.8-flash-lite-tts"
        selected_voice = voice or "Puck"
        if not supports_gemini_voice(resolved_model, selected_voice):
            raise ValueError(f"Unsupported Gemini TTS voice: {selected_voice}")
        super().__init__(
            sample_rate=sample_rate,
            settings=TTSSettings(model=resolved_model, voice=selected_voice, language=None),
            **kwargs,
        )
        self._api_key = api_key or ""
        self._model = resolved_model
        self._voice = selected_voice
        self._sample_rate = sample_rate
        # Gemini's raw output is 24kHz even when a transport requests 8/16kHz.
        # Frames must carry the source rate so the transport can resample;
        # relabelling 24kHz as 16kHz slows speech and changes its pitch.
        self._provider_sample_rate = 24000

    def can_generate_metrics(self) -> bool:
        return True

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        logger.debug(
            f"[Gemini TTS] Synthesizing {len(text)} chars with {self._model}/{self._voice}"
        )
        await self.start_tts_usage_metrics(text)
        yield TTSStartedFrame(context_id=context_id)

        is_streaming_model = self._model.startswith("gemini-3.8-")
        method = "streamGenerateContent" if is_streaming_model else "generateContent"
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:{method}"
        )
        if is_streaming_model:
            url += "?alt=sse"
            payload = {
                "contents": [{
                    "role": "user",
                    "parts": [{
                        "text": text,
                        "speech_metadata": {
                            "style": "natural, relaxed conversational delivery with clear articulation"
                        },
                    }],
                }],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "responseFormat": {
                        "audio": {
                            "mimeType": "AUDIO_L16",
                            "sampleRate": self._provider_sample_rate,
                        }
                    },
                    "speechConfig": {"voiceConfig": {"voice": self._voice}},
                },
            }
        else:
            payload = {
                "contents": [{"parts": [{"text": text}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {"voiceName": self._voice}
                        }
                    },
                },
            }

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }
        audio_emitted = False

        async def audio_frames(response_data: dict) -> AsyncGenerator[Frame, None]:
            nonlocal audio_emitted
            for candidate in response_data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    inline_data = part.get("inlineData") or part.get("inline_data") or {}
                    encoded = inline_data.get("data")
                    if not encoded:
                        continue
                    audio_bytes = base64.b64decode(encoded)
                    mime_type = inline_data.get("mimeType") or inline_data.get("mime_type") or ""
                    rate = re.search(r"(?:^|;)\s*rate\s*=\s*(\d+)", mime_type, re.IGNORECASE)
                    sample_rate = int(rate.group(1)) if rate else self._provider_sample_rate
                    if not 8000 <= sample_rate <= 192000:
                        raise ValueError("Gemini TTS returned an invalid audio sample rate")
                    if audio_bytes.startswith(b"RIFF") and b"WAVE" in audio_bytes[:16]:
                        try:
                            with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
                                sample_rate = wav_file.getframerate() or sample_rate
                                audio_bytes = wav_file.readframes(wav_file.getnframes())
                        except (wave.Error, EOFError):
                            logger.warning("[Gemini TTS] Could not parse returned WAV header")
                    if audio_bytes:
                        audio_emitted = True
                        yield TTSAudioRawFrame(
                            audio=audio_bytes,
                            sample_rate=sample_rate,
                            num_channels=1,
                            context_id=context_id,
                        )

        try:
            async with aiohttp.ClientSession() as session:
                for attempt in range(2):
                    async with session.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=12),
                    ) as response:
                        if response.status != 200:
                            detail = (await response.text())[:500]
                            if response.status == 503 and attempt == 0:
                                logger.warning("[Gemini TTS] Provider busy; retrying once")
                            else:
                                logger.error("[Gemini TTS] HTTP {}: {}", response.status, detail)
                                yield ErrorFrame(error=f"Gemini TTS error: {response.status}")
                                return
                        else:
                            if is_streaming_model:
                                async for line in response.content:
                                    line = line.strip()
                                    if not line or not line.startswith(b"data:"):
                                        continue
                                    event_data = line[5:].strip()
                                    if event_data == b"[DONE]":
                                        break
                                    try:
                                        event = json.loads(event_data)
                                    except (json.JSONDecodeError, UnicodeDecodeError):
                                        logger.debug("[Gemini TTS] Ignoring malformed stream event")
                                        continue
                                    async for frame in audio_frames(event):
                                        yield frame
                            else:
                                result = await response.json()
                                async for frame in audio_frames(result):
                                    yield frame
                            if not audio_emitted:
                                yield ErrorFrame(error="Gemini TTS returned no audio data")
                            return
                    await asyncio.sleep(0.25)
        except Exception as error:
            logger.error("[Gemini TTS] Synthesis failed: {}", type(error).__name__)
            yield ErrorFrame(error=str(error))
        finally:
            yield TTSStoppedFrame(context_id=context_id)
