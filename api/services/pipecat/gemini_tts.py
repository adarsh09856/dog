"""Google Gemini Direct Audio Text-to-Speech service for Pipecat.

Allows using Google AI Studio API keys directly for gemini-2.5-flash-preview-tts
without requiring Google Cloud service account JSON credentials.
"""

from collections.abc import AsyncGenerator
import aiohttp
from loguru import logger

from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.services.tts_service import TTSService
from pipecat.utils.tracing.service_decorators import traced_tts


class GeminiTTSService(TTSService):
    """Direct Google Gemini TTS service using simple AI Studio API key."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash-preview-tts",
        voice: str = "Puck",
        sample_rate: int = 24000,
        **kwargs,
    ):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._api_key = api_key or ""
        self._model = model
        self._voice = voice
        self._sample_rate = sample_rate

    def can_generate_metrics(self) -> bool:
        return True

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        logger.debug(f"[Gemini TTS] Synthesizing: '{text[:40]}...' with voice '{self._voice}'")
        await self.start_tts_usage_metrics(text)
        yield TTSStartedFrame(context_id=context_id)

        # Connect to Google Gemini API
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent?key={self._api_key}"
        headers = {
            "Content-Type": "application/json",
        }
        payload = {
            "contents": [
                {
                    "parts": [{"text": text}]
                }
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": self._voice
                        }
                    }
                }
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.error(f"[Gemini TTS] Error {resp.status}: {err_text}")
                        yield ErrorFrame(error=f"Gemini TTS error: {resp.status}")
                        yield TTSStoppedFrame(context_id=context_id)
                        return

                    res_json = await resp.json()
                    candidates = res_json.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for part in parts:
                            inline_data = part.get("inlineData", {})
                            if inline_data.get("mimeType", "").startswith("audio/"):
                                import base64
                                import io
                                import wave
                                audio_bytes = base64.b64decode(inline_data.get("data", ""))

                                # If Google returns a WAV container, extract raw PCM frames
                                if audio_bytes.startswith(b"RIFF") and b"WAVE" in audio_bytes[:16]:
                                    try:

                                        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                                            actual_rate = wf.getframerate()
                                            raw_pcm = wf.readframes(wf.getnframes())
                                            yield TTSAudioRawFrame(
                                                audio=raw_pcm,
                                                sample_rate=actual_rate or self._sample_rate,
                                                num_channels=1,
                                                context_id=context_id,
                                            )
                                            continue
                                    except Exception as wav_err:
                                        logger.warning(f"[Gemini TTS] WAV parse failed, yielding raw: {wav_err}")

                                yield TTSAudioRawFrame(
                                    audio=audio_bytes,
                                    sample_rate=self._sample_rate,
                                    num_channels=1,
                                    context_id=context_id,
                                )


        except Exception as e:
            logger.error(f"[Gemini TTS] Exception: {e}")
            yield ErrorFrame(error=str(e))
        finally:
            await self.stop_tts_usage_metrics()
            yield TTSStoppedFrame(context_id=context_id)
