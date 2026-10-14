"""Piper HTTP service with a call-owned connection lifecycle."""

import aiohttp

from pipecat.services.piper.tts import PiperHttpTTSService


class PiperOwnedSessionTTSService(PiperHttpTTSService):
    """Close the session created by the service factory when a visit ends."""

    def __init__(self, *args, aiohttp_session: aiohttp.ClientSession, **kwargs):
        super().__init__(*args, aiohttp_session=aiohttp_session, **kwargs)
        self._owned_session = aiohttp_session

    async def cleanup(self):
        try:
            await super().cleanup()
        finally:
            if not self._owned_session.closed:
                await self._owned_session.close()
