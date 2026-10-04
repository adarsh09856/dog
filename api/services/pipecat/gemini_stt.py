"""Google Gemini Speech-to-Text service for Pipecat.

Uses Google Gemini 2.5 Flash / 1.5 Flash multimodal audio understanding
to transcribe speech from audio chunks using the Gemini API key.
"""

import base64
import io
import time
import wave
from collections.abc import AsyncGenerator
import aiohttp
from loguru import logger

from pipecat.frames.frames import (
    Frame,
    TranscriptionFrame,
)
from pipecat.services.stt_service import STTService


class GeminiSTTService(STTService):
    """Google Gemini multimodal Speech-to-Text service."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gemini-3.8-flash",
        language: str = "en",
        sample_rate: int = 16000,
        **kwargs,
    ):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._api_key = api_key or ""
        self._model = "gemini-3.8-flash" if (not model or "stt" in model.lower() or model in ("default", "none") or "2.5" in model) else model
        self._language = language
        self._sample_rate = sample_rate

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        if not self._api_key:
            logger.warning("[Gemini STT] Cannot transcribe: missing Gemini API key")
            return

        if not audio or len(audio) < 1000:
            return

        # Prepare WAV container from raw PCM bytes
        try:
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self._sample_rate)
                wf.writeframes(audio)
            wav_bytes = wav_buffer.getvalue()
        except Exception as e:
            logger.debug(f"[Gemini STT] Error packaging WAV: {e}")
            wav_bytes = audio

        encoded_audio = base64.b64encode(wav_bytes).decode("utf-8")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent?key={self._api_key}"

        prompt = (
            f"Transcribe the spoken words in this audio clip verbatim into text in language '{self._language}'. "
            "Output ONLY the exact transcribed text, nothing else. If there is only silence, background noise, or no clear speech, output nothing."
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": "audio/wav",
                                "data": encoded_audio,
                            }
                        },
                        {"text": prompt},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 200,
            },
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            content = candidates[0].get("content", {})
                            parts = content.get("parts", [])
                            text = "".join(p.get("text", "") for p in parts).strip()
                            # Clean unwanted preamble if any
                            if text and text.lower() not in ("none", "silence", "noise", "none."):
                                logger.info(f"[Gemini STT] Transcribed: '{text}'")
                                yield TranscriptionFrame(
                                    text=text,
                                    user_id="caller",
                                    timestamp=time.time(),
                                )
                    else:
                        err_body = await resp.text()
                        logger.warning(f"[Gemini STT] API error {resp.status}: {err_body[:200]}")
        except Exception as e:
            logger.warning(f"[Gemini STT] Exception during transcription: {e}")
