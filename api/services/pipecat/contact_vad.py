"""VAD endpointing tuned for explicit caller phone-number dictation."""

from collections.abc import Callable

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams, VADState


class ContactAwareSileroVADAnalyzer(SileroVADAnalyzer):
    """Use a longer silence threshold only while collecting a phone number."""

    def __init__(self, *, phone_pending: Callable[[], bool], **kwargs):
        super().__init__(**kwargs)
        self._phone_pending = phone_pending
        self._ordinary_stop_secs = self.params.stop_secs

    async def analyze_audio(self, buffer: bytes) -> VADState:
        desired_stop_secs = 0.55 if self._phone_pending() else self._ordinary_stop_secs
        if (
            self.params.stop_secs != desired_stop_secs
            and self._vad_state == VADState.QUIET
        ):
            self.set_params(self.params.model_copy(update={"stop_secs": desired_stop_secs}))
        return await super().analyze_audio(buffer)
