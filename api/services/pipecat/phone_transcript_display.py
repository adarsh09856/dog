"""Display confidently parsed phone digits alongside the original speech."""

import re


def phone_transcript_display(text: str, *, awaiting_phone: bool) -> str:
    if not awaiting_phone or not text:
        return text

    # These ASR substitutions are useful for a later confirmation, but are not
    # reliable enough to display as if the caller clearly said a digit.
    if re.search(r"\b(?:on|run|won|wan)\b", text, re.IGNORECASE):
        return text

    from api.services.workflow.contact_context import caller_phone_fragment_reply

    # Parse into throwaway call-scoped state. Never mutate the actual transcript,
    # contact data, workflow, or confirmation state just to format the display.
    state = {"awaiting_phone": True, "reply_language": "English"}
    caller_phone_fragment_reply([{"role": "user", "content": text}], state)
    if state.get("replace_phone_digits_on_next_turn") or state.get("caller_phone_pending_double"):
        return text
    digits = state.get("caller_phone") or state.get("caller_phone_digits")
    if not isinstance(digits, str) or len(digits) < 3:
        return text
    label = "अंक" if re.search(r"[\u0900-\u097f]", text) else "digits"
    return f"{text} ({label}: {digits})"
