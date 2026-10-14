"""Piper HTTP service with a call-owned connection lifecycle."""

import aiohttp
from loguru import logger

from pipecat.frames.frames import ErrorFrame, TTSAudioRawFrame
from pipecat.services.piper.tts import PiperHttpTTSService


class PiperOwnedSessionTTSService(PiperHttpTTSService):
    """Close the session created by the service factory when a visit ends."""

    def __init__(self, *args, aiohttp_session: aiohttp.ClientSession, **kwargs):
        super().__init__(*args, aiohttp_session=aiohttp_session, **kwargs)
        self._owned_session = aiohttp_session

    async def run_tts(self, text: str, context_id: str):
        # The configured voice was selected from the catalog. Piper's synthesis
        # endpoint validates it again and returns an HTTP error if it is gone.
        # Avoid a separate /voices request on every new call: that request can
        # consume the entire first-speech timeout while Piper is busy.
        self._validated_voice = self._settings.voice

        for attempt in range(2):
            audio_received = False
            errors = []
            async for frame in super().run_tts(text, context_id):
                if isinstance(frame, TTSAudioRawFrame):
                    audio_received = True
                if isinstance(frame, ErrorFrame):
                    errors.append(frame)
                    continue
                yield frame
            if audio_received:
                return
            if attempt == 0:
                logger.warning("Piper produced no audio for context {}; retrying once", context_id)
                continue
            for error in errors:
                yield error
            if not errors:
                yield ErrorFrame(error="Piper produced no audio after two attempts")

    async def cleanup(self):
        try:
            await super().cleanup()
        finally:
            if not self._owned_session.closed:
                await self._owned_session.close()
