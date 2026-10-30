"""Callback factory helpers for :pyclass:`~api.services.workflow.pipecat_engine.PipecatEngine`.

Each helper takes a :class:`PipecatEngine` instance and returns an async
callback function suitable for passing to the various pipeline processors.
Separating these helpers into their own module keeps
``pipecat_engine.py`` focused on high-level engine orchestration logic while
encapsulating the callback implementations here for easier maintenance and
unit-testing.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger
from pipecat.frames.frames import (
    LLMMessagesAppendFrame,
)
from pipecat.utils.enums import EndTaskReason

if TYPE_CHECKING:
    from api.services.workflow.pipecat_engine import PipecatEngine


# ---------------------------------------------------------------------------
# User-idle handling
# ---------------------------------------------------------------------------


async def handle_user_idle(engine: "PipecatEngine", aggregator, attempt: int) -> None:
    """Give one short idle prompt without another expensive conversation turn."""
    logger.debug(f"Handling user_idle, attempt: {attempt}")
    if getattr(engine, "_is_realtime", False):
        # Speech-to-speech providers own their output path; keep their native
        # response mechanism. Local text LLM pipelines use fixed TTS below.
        content = (
            "The user has been quiet. Continue the existing conversation naturally: "
            "do not greet or introduce yourself again. Ask one short check-in question "
            "in the language the caller used most recently."
            if attempt == 1
            else "The user has been quiet and this call is ending. Do not greet or "
            "introduce yourself again. Give one short, polite goodbye in the language "
            "the caller used most recently."
        )
        await aggregator.push_frame(
            LLMMessagesAppendFrame([{"role": "system", "content": content}], run_llm=True)
        )
    else:
        language = _idle_prompt_language(engine)
        phrases = {
            "hi": (
                "क्या आपको थोड़ा और समय चाहिए?",
                "धन्यवाद। आपका दिन शुभ हो।",
            ),
            "en": (
                "Would you like a little more time?",
                "Thank you. Have a good day.",
            ),
        }
        phrase_set = phrases.get(language)
        if phrase_set:
            engine.call_monitor.expect_idle_prompt()
            speech = await engine.queue_speech(
                phrase_set[0 if attempt == 1 else 1],
                mute_user=attempt > 1,
                timeout=15,
            )
            # On the final idle attempt, don't close the call while the goodbye
            # is still in the TTS/output queue.
            if attempt > 1:
                await speech.wait()
        else:
            logger.info(
                "Skipping generated idle speech because the caller language "
                "has no safe fixed prompt"
            )
            engine.call_monitor.skip_idle_prompt()
    if attempt > 1:
        await engine.end_call_with_reason(
            EndTaskReason.USER_IDLE_MAX_DURATION_EXCEEDED.value
        )


def _idle_prompt_language(engine: "PipecatEngine") -> str | None:
    """Resolve only Hindi or English for the fixed local idle prompts."""
    agent = getattr(engine, "active_agent", None)
    llm = getattr(agent, "llm", None)
    source = getattr(llm, "_caller_language_source", None)
    latest_text = getattr(source, "latest_detected_text", None)
    if isinstance(latest_text, str) and any("\u0900" <= char <= "\u097f" for char in latest_text):
        return "hi"

    candidates = [getattr(source, "latest_detected_language", None)]
    settings = getattr(source, "_settings", None)
    candidates.append(getattr(settings, "language", None))
    user_config = getattr(agent, "user_config", None)
    for service_name in ("stt", "tts"):
        service = getattr(user_config, service_name, None)
        candidates.append(getattr(service, "language", None))
    for candidate in candidates:
        if candidate is None:
            continue
        code = str(candidate).strip().lower().replace("_", "-").split(".")[-1]
        code = code.split("-", 1)[0]
        if code in {"hi", "en"}:
            return code
    return None


# ---------------------------------------------------------------------------
# Max-duration handling
# ---------------------------------------------------------------------------


def create_max_duration_callback(engine: "PipecatEngine"):
    """Return a callback that cancels the task when the hard call limit is exceeded."""

    async def handle_max_duration():
        logger.debug("Max call duration exceeded. Terminating call")
        await engine.end_call_with_reason(
            EndTaskReason.CALL_DURATION_EXCEEDED.value,
            abort_immediately=True,
        )

    return handle_max_duration


# ---------------------------------------------------------------------------
# Generation-started handling
# ---------------------------------------------------------------------------


def create_generation_started_callback(
    engine: "PipecatEngine", *, visit_id: str | None = None
):
    """Return a callback that resets flags at the start of each LLM generation.

    Args:
        engine: The call's engine.
        visit_id: The agent visit whose generation stage fires this. A
            generation starting in an agent that has already handed the call
            over is ignored, so it cannot clear the reference text the new
            agent is mid-way through building.
    """

    async def handle_generation_started():
        if not engine.owns_generation(visit_id):
            logger.debug(f"Ignoring generation start from retired visit {visit_id}")
            return
        logger.debug("LLM generation started in callback processor")
        # Clear reference text from previous generation
        engine._current_llm_generation_reference_text = ""

    return handle_generation_started


def create_aggregation_correction_callback(engine: "PipecatEngine"):
    """Create a callback that uses engine's reference text to correct corrupted aggregation."""

    def correct_corrupted_aggregation(ref: str, corrupted: str) -> str:
        """Correct corrupted text by aligning it with reference text.

        This is a pure function that doesn't depend on engine instance.
        """
        # 1) Safety check: if ref (minus spaces) is shorter than corrupted, bail out
        # also if corrupted is less than 10 characters, lets also return that since most likely
        # Elevenlabs returned the right alignment
        alnum_corr = "".join(ch for ch in corrupted if ch.isalnum())
        alnum_ref = "".join(ch for ch in ref if ch.isalnum())

        if corrupted in ref or len(alnum_ref) < len(alnum_corr) or len(alnum_corr) < 10:
            return corrupted

        logger.debug(
            f"In correct_corrupted_aggregation: ref: {ref} corrupted: {corrupted}"
        )

        # 2) Find where in `ref` we should start aligning.
        #    We take the first N (N=10) characters of `corrupted`
        #    and look for all their occurrences in `ref`.
        #    We pick the *last* one
        prefix = corrupted[:10]

        # find all start‐indices of that prefix in ref
        starts = [m.start() for m in re.finditer(re.escape(prefix), ref)]
        start_idx = starts[-1] if starts else 0

        # 3) Now run the same two‑pointer scan from start_idx
        i, j = start_idx, 0
        out_chars = []
        while i < len(ref) and j < len(corrupted):
            r_ch, c_ch = ref[i], corrupted[j]
            if r_ch == c_ch:
                out_chars.append(r_ch)
                i += 1
                j += 1

            elif c_ch == " ":
                # extra space in corrupted → skip it
                j += 1

            elif r_ch == " " or r_ch in ".,;:!?":
                # missing structural char in corrupted → emit from ref
                out_chars.append(r_ch)
                i += 1

            else:
                # letter mismatch → best‑effort copy from ref
                out_chars.append(r_ch)
                i += 1
                j += 1

        # 4) A final check - the final created output should be exactly
        # as corrupted sentence sans whitespace.
        alnum_out = "".join([ch for ch in out_chars if ch.isalnum()])
        if alnum_out != alnum_corr:
            return corrupted

        # 5) Join and return exactly what we built
        return "".join(out_chars)

    def correct_aggregation(corrupted: str) -> str:
        reference = engine._current_llm_generation_reference_text

        if not reference:
            return corrupted

        # Apply the correction algorithm
        corrected = correct_corrupted_aggregation(reference, corrupted)
        return corrected

    return correct_aggregation
