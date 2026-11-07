"""Start local inference during the caller's normal pause window."""

from collections.abc import Callable

from pipecat.frames.frames import EagerEndOfTurnCancelFrame, InterimTranscriptionFrame
from pipecat.turns.types import UserTurnSpeculation
from pipecat.turns.user_stop.speech_timeout_user_turn_stop_strategy import (
    SpeechTimeoutUserTurnStopStrategy,
)


def _same_confirmed_utterance(speculative: str, confirmed: str) -> bool:
    """Ignore transcript whitespace and terminal punctuation normalization.

    Local STT can append punctuation or normalize whitespace when the same
    utterance is committed. Those formatting changes should not throw away a
    completed speculative model request and force a second inference.
    """
    def normalize(text: str) -> str:
        normalized = " ".join(str(text or "").split())
        return normalized.rstrip(".,!?;:।॥…؟،").rstrip()

    return normalize(speculative) == normalize(confirmed)


class SpeculativeLocalTurnStopStrategy(SpeechTimeoutUserTurnStopStrategy):
    """Prepare a provisional local reply without shortening the pause window.

    Pipecat's LLM speculation gate holds response frames until turn confirmation
    and cancels them if speech resumes. Tool calls are cancelled by the LLM
    service, so provisional inference cannot commit actions.
    """

    def __init__(
        self,
        *,
        can_speculate: Callable[[str], bool] | None = None,
        speech_timeout: Callable[[], float] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._local_speculation: UserTurnSpeculation | None = None
        self._can_speculate = can_speculate
        self._speech_timeout = speech_timeout

    def _apply_speech_timeout(self):
        if self._speech_timeout is not None:
            self._user_speech_timeout = max(0.0, float(self._speech_timeout()))

    async def _withdraw(self):
        if self._local_speculation is not None:
            self._local_speculation = None
            await self.trigger_user_turn_speculation_cancelled()

    async def process_frame(self, frame):
        if isinstance(frame, EagerEndOfTurnCancelFrame):
            # A tool request cancels speculation; confirmed inference must run.
            self._local_speculation = None
        elif isinstance(frame, InterimTranscriptionFrame):
            # New speech invalidates a previously-final segment until STT
            # finalizes the expanded utterance.
            await self._withdraw()
        return await super().process_frame(frame)

    async def _maybe_start_speculation(self):
        if (
            self._local_speculation is None
            and self._transcript_finalized
            and self._text.strip()
            and self._vad_stopped
            and not self._vad_user_speaking
            and not self._user_speech_wait_done
            and (self._can_speculate is None or self._can_speculate(self._text))
        ):
            self._local_speculation = UserTurnSpeculation(text=self._text)
            await self.trigger_user_turn_inference_triggered(
                speculation=self._local_speculation
            )

    async def _handle_transcription(self, frame):
        if self._local_speculation is not None:
            await self._withdraw()
        self._apply_speech_timeout()
        await super()._handle_transcription(frame)
        await self._maybe_start_speculation()

    async def _handle_vad_user_stopped_speaking(self, frame):
        self._apply_speech_timeout()
        await super()._handle_vad_user_stopped_speaking(frame)
        await self._maybe_start_speculation()

    async def _handle_vad_user_started_speaking(self, frame):
        await self._withdraw()
        await super()._handle_vad_user_started_speaking(frame)

    async def trigger_user_turn_stopped(self, *, enable_user_speaking_frames=None):
        candidate = self._local_speculation
        if candidate is not None and _same_confirmed_utterance(candidate.text, self._text):
            self._local_speculation = None
            await self.trigger_user_turn_finalized(
                enable_user_speaking_frames=enable_user_speaking_frames,
                confirms_speculation=True,
            )
        else:
            await self._withdraw()
            await super().trigger_user_turn_stopped(
                enable_user_speaking_frames=enable_user_speaking_frames
            )

    async def _reset(self, *, clear_vad_user_speaking):
        await self._withdraw()
        await super()._reset(clear_vad_user_speaking=clear_vad_user_speaking)

    async def cleanup(self):
        await self._withdraw()
        await super().cleanup()
