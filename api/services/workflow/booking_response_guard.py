"""Keep text-chat booking claims tied to a successful calendar write."""

import re

_SAVED_CLAIM = re.compile(
    r"(?:\b(?:saved|booked|scheduled|confirmed)\b.{0,100}\b(?:appointment|booking|consultation|reservation)\b"
    r"|\b(?:appointment|booking|consultation|reservation)\b.{0,100}\b(?:saved|booked|scheduled|confirmed)\b"
    r"|appointment\s+id\s+is)"
    r"|(?:अपॉइंटमेंट|बुकिंग|नियुक्ति).{0,60}(?:बुक हो गई|बुक कर दी|पक्की हो गई|पुष्टि हो गई|पुष्टि कर दी|सहेज दी|सेव हो गई)",
    re.IGNORECASE | re.DOTALL,
)

UNVERIFIED_BOOKING_REPLY = (
    "I could not verify a saved appointment in the calendar. "
    "No booking has been confirmed. Please try again or ask for another time."
)


def guard_booking_reply(reply: str | None, events: list[dict], *, language: str | None = None) -> str | None:
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
            if (language or "").split("-")[0] == "hi":
                return (
                    "आपकी अपॉइंटमेंट बुक हो गई है। "
                    f"बुकिंग नंबर: {result['appointment_id']}। "
                    f"समय: {result.get('start_time', 'अपॉइंटमेंट कैलेंडर में देखें')}।"
                )
            return (
                "Your appointment is booked. "
                f"Appointment ID: {result['appointment_id']}. "
                f"Time: {result.get('start_time', 'see the appointments calendar')}."
            )
    if (language or "").split("-")[0] == "hi":
        return "कैलेंडर में आपकी बुकिंग की पुष्टि नहीं हो सकी। कृपया विवरण जाँचकर फिर कोशिश करें।"
    return UNVERIFIED_BOOKING_REPLY
