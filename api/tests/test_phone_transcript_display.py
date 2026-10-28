"""Live number display must not rewrite or guess the recognized speech."""

from types import SimpleNamespace

from api.services.pipecat.realtime_feedback_observer import RealtimeFeedbackObserver
from pipecat.frames.frames import TranscriptionFrame
from pipecat.observers.base_observer import FramePushed
from pipecat.processors.frame_processor import FrameDirection


async def observed(text, pending):
    events = []

    async def send(event):
        events.append(event)

    observer = RealtimeFeedbackObserver(ws_sender=send, phone_pending=lambda: pending)
    frame = TranscriptionFrame(text, user_id="caller", timestamp="2026-10-27T00:00:00Z")
    await observer.on_push_frame(FramePushed(
        source=SimpleNamespace(), destination=SimpleNamespace(), frame=frame,
        direction=FrameDirection.UPSTREAM, timestamp=0,
    ))
    return frame.text, events[0]["payload"]["text"]


async def test_full_phone_displays_digits_and_preserves_recognized_words():
    original = "Nine-five, three-eight-three, double-zero, nine-four-one."
    frame, display = await observed(original, True)
    assert frame == original
    assert display.startswith(original)
    assert "9538300941" in display


async def test_incomplete_digits_can_be_displayed_without_inventing_the_rest():
    original = "three, eight, three"
    frame, display = await observed(original, True)
    assert frame == original
    assert display.endswith("(digits: 383)")


async def test_unrecognized_or_ambiguous_words_are_not_converted():
    for original in ["nine-five pre-ed pre-double-zero-nine-four-one", "nine four run", "double"]:
        frame, display = await observed(original, True)
        assert frame == display == original


async def test_normal_conversation_is_not_treated_as_phone_dictation():
    original = "three, eight, three"
    frame, display = await observed(original, False)
    assert frame == display == original


async def test_regional_spoken_digits_display_in_arabic_digit_form():
    original = "नाइन फाइव थ्री आइट थ्री डबल ज़ीरो नाइन फोर वन"
    frame, display = await observed(original, True)
    assert frame == original
    assert "9538300941" in display
