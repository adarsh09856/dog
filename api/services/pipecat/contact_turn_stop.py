"""Allow natural pauses while the caller dictates a requested phone number."""

from collections.abc import Callable

from pipecat.turns.user_stop.speech_timeout_user_turn_stop_strategy import (
    SpeechTimeoutUserTurnStopStrategy,
)


class ContactAwareTurnStopStrategy(SpeechTimeoutUserTurnStopStrategy):
    def __init__(self, *, phone_pending: Callable[[], bool], **kwargs):
        super().__init__(**kwargs)
        self._phone_pending = phone_pending
        self._ordinary_speech_timeout = self._user_speech_timeout

    def _apply_contact_timeout(self):
        self._user_speech_timeout = (
            max(1.2, self._ordinary_speech_timeout)
            if self._phone_pending() else self._ordinary_speech_timeout
        )

    async def _handle_transcription(self, frame):
        self._apply_contact_timeout()
        await super()._handle_transcription(frame)

    async def _handle_vad_user_stopped_speaking(self, frame):
        self._apply_contact_timeout()
        await super()._handle_vad_user_stopped_speaking(frame)
