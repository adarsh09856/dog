"""Keep text-chat booking claims tied to a successful calendar write."""

import re

_SAVED_CLAIM = re.compile(
    r"(?:\b(?:saved|booked|scheduled|confirmed)\b.{0,100}\b(?:appointment|booking|consultation|reservation)\b"
    r"|\b(?:appointment|booking|consultation|reservation)\b.{0,100}\b(?:saved|booked|scheduled|confirmed)\b"
    r"|appointment\s+id\s+is)"
    r"|(?:अपॉइंटमेंट|बुकिंग|नियुक्ति).{0,60}(?:पक्क|बुक|सेव|कन्फर्म)",
    re.IGNORECASE | re.DOTALL,
)

UNVERIFIED_BOOKING_REPLY = (
    "I could not verify a saved appointment in the calendar. "
    "No booking has been confirmed. Please try again or ask for another time."
)


def guard_booking_reply(reply: str | None, events: list[dict]) -> str | None:
    """Replace an unsupported success claim; never turn an action failure into success."""
    if not reply or not _SAVED_CLAIM.search(reply):
        return reply
    for event in events:
        if event.get("type") != "tool_call_result":
            continue
        payload = event.get("payload") or {}
        if payload.get("function_name") != "book_appointment":
            continue
        result = payload.get("result") or {}
        if isinstance(result, dict) and result.get("booked") is True and result.get("appointment_id"):
            return reply
    return UNVERIFIED_BOOKING_REPLY
