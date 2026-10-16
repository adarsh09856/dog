"""Extract an explicit, fully specified booking instruction for direct execution."""

import re
from datetime import datetime, timedelta, timezone

_CONFIRM = re.compile(r"\bconfirm(?:ed)?\b|पुष्टि\s+करत[ाी]\s+हूँ", re.IGNORECASE)
_SAVE = re.compile(r"\b(?:save|book|schedule)\b|बुक\s+कर", re.IGNORECASE)
_NEGATE = re.compile(r"\b(?:do not|don't|not now|cancel|stop|never)\b|\bno\s+booking\b|नहीं|मत\s", re.IGNORECASE)
_NAME = re.compile(r"\b(?:name\s*[:\-]?|for)\s+([A-Za-z][A-Za-z .'-]{1,98}?)(?=,\s*(?:phone|\+)|\s+phone\b)", re.IGNORECASE)
_PHONE = re.compile(r"\+\d{10,15}\b")
_WHEN = re.compile(
    r"\b(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})\s+at\s+(\d{1,2}):(\d{2})\s*(AM|PM)\b",
    re.IGNORECASE,
)
_OFFSET = re.compile(r"UTC\s*([+-])(\d{1,2}):?(\d{2})\b", re.IGNORECASE)
_IST = re.compile(r"\bIST\b|\bAsia/Kolkata\b", re.IGNORECASE)
_HINGLISH_NAME = re.compile(
    r"\bmera\s+naam\s+([A-Za-z][A-Za-z .'-]{1,98}?)(?=,\s*(?:phone|number)|\s+(?:phone|number)\b)",
    re.IGNORECASE,
)
_HINGLISH_WHEN = re.compile(
    r"\b(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})\s*,?\s*(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\b",
    re.IGNORECASE,
)
_HINDI_NAME = re.compile(
    r"(?:मेरा नाम\s+([^,।\d]+?)\s+है|मैं\s+([^,।\d]+?)\s+(?:अपॉइंटमेंट|बुकिंग))"
)
_HINDI_MONTHS = ("जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर")
_HINDI_WHEN = re.compile(
    r"(\d{1,2})\s+(" + "|".join(_HINDI_MONTHS) + r")\s+(\d{4})\s*(?:को\s*)?"
    r"(सुबह|दोपहर|शाम|रात)\s+(\d{1,2}):(\d{2})\s*बजे"
)
_BOOKING_REQUEST = re.compile(
    r"\b(?:book|schedule|make|set\s+up)\b.{0,45}\b(?:appointment|booking|consultation)\b"
    r"|\b(?:appointment|booking|consultation)\b.{0,30}\b(?:book|schedule)\b"
    r"|अपॉइंटमेंट.{0,24}(?:बुक|रख)|बुकिंग.{0,24}(?:कर|चाहत)|"
    r"\b(?:appointment|booking)\s+(?:book|schedule)\s+kar(?:na|ni)?\b",
    re.IGNORECASE,
)
_CALLER_NAME = re.compile(
    r"\b(?:my name is|i'm|this is|mera naam)\s+[A-Za-z][A-Za-z .'-]{1,50}"
    r"|मेरा नाम\s*[^,।\d]{2,50}",
    re.IGNORECASE,
)


def first_booking_question(messages: list[dict]) -> str | None:
    """Return one fast, language-matched name question for a first booking turn."""
    user_messages = [
        message for message in messages
        if isinstance(message, dict) and message.get("role") == "user"
    ]
    if not user_messages:
        return None
    content = user_messages[-1].get("content")
    caller_text = content if isinstance(content, str) else ""
    if any(
        isinstance(message.get("content"), str)
        and _CALLER_NAME.search(message["content"])
        for message in user_messages
    ):
        return None
    if not _BOOKING_REQUEST.search(caller_text) or _CALLER_NAME.search(caller_text):
        return None
    if re.search(r"[\u0900-\u097f]", caller_text):
        return "ज़रूर। अपॉइंटमेंट किस नाम से बुक करूँ?"
    if re.search(r"\b(?:mujhe|mera|naam|karna|chahiye|haan)\b", caller_text, re.IGNORECASE):
        return "Bilkul. Appointment kis naam se book karun?"
    return "Sure. What name should I use for the appointment?"


def confirmed_booking_arguments(message: str) -> dict | None:
    """Accept only a bounded confirmation with name, E.164 phone and zoned time.

    Other natural-language requests stay on the conversational path. A failed
    parse never authorizes a calendar write.
    """
    message = message.translate(str.maketrans("०१२३४५६७८९", "0123456789"))
    if not (_CONFIRM.search(message) and _SAVE.search(message)) or _NEGATE.search(message):
        return None
    name = _NAME.search(message)
    phone = _PHONE.search(message)
    when = _WHEN.search(message)
    hindi_name = _HINDI_NAME.search(message)
    hindi_when = _HINDI_WHEN.search(message)
    hinglish_name = _HINGLISH_NAME.search(message)
    hinglish_when = _HINGLISH_WHEN.search(message)
    offset = _OFFSET.search(message)
    ist = _IST.search(message)
    if not phone or not (offset or ist) or not (
        (name and when) or (hindi_name and hindi_when) or (hinglish_name and hinglish_when)
    ):
        return None
    if offset:
        sign, hours, minutes = offset.groups()
        hours, minutes = int(hours), int(minutes)
        if hours > 14 or minutes > 59 or (hours == 14 and minutes != 0):
            return None
        tz = timezone(timedelta(minutes=(1 if sign == "+" else -1) * (hours * 60 + minutes)))
    else:
        tz = timezone(timedelta(hours=5, minutes=30))
    try:
        if name and when:
            day, month, year, hour, minute, meridian = when.groups()
            parsed = datetime.strptime(
                f"{day} {month} {year} {hour}:{minute} {meridian.upper()}",
                "%d %B %Y %I:%M %p",
            ).replace(tzinfo=tz)
            customer_name = name.group(1).strip(" .,;:")
        elif hindi_name and hindi_when:
            day, month, year, period, hour, minute = hindi_when.groups()
            hour = int(hour)
            if not 1 <= hour <= 12 or (period == "रात" and hour < 12):
                return None  # Night dates require clarification rather than a guessed day.
            hour = hour % 12 + (12 if period in ("दोपहर", "शाम") else 0)
            parsed = datetime(int(year), _HINDI_MONTHS.index(month) + 1, int(day), hour, int(minute), tzinfo=tz)
            customer_name = next(part for part in hindi_name.groups() if part).strip()
        else:
            day, month, year, hour, minute, meridian = hinglish_when.groups()
            parsed = datetime.strptime(
                f"{day} {month} {year} {hour}:{minute or '00'} {meridian.upper()}",
                "%d %B %Y %I:%M %p",
            ).replace(tzinfo=tz)
            customer_name = hinglish_name.group(1).strip(" .,;:")
    except ValueError:
        return None
    if len(customer_name) < 2 or customer_name.startswith("["):
        return None
    return {
        "customer_name": customer_name,
        "customer_phone": phone.group(),
        "start_time": parsed.isoformat(),
        "confirmed_by_caller": True,
    }
