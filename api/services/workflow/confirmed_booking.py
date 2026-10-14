"""Extract an explicit, fully specified booking instruction for direct execution."""

import re
from datetime import datetime, timedelta, timezone

_CONFIRM = re.compile(r"\bconfirm(?:ed)?\b", re.IGNORECASE)
_SAVE = re.compile(r"\b(?:save|book|schedule)\b", re.IGNORECASE)
_NEGATE = re.compile(r"\b(?:do not|don't|not now|cancel|stop|never)\b|\bno\s+booking\b", re.IGNORECASE)
_NAME = re.compile(r"\b(?:name\s*[:\-]?|for)\s+([A-Za-z][A-Za-z .'-]{1,98}?)(?=,\s*(?:phone|\+)|\s+phone\b)", re.IGNORECASE)
_PHONE = re.compile(r"\+\d{10,15}\b")
_WHEN = re.compile(
    r"\b(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})\s+at\s+(\d{1,2}):(\d{2})\s*(AM|PM)\b",
    re.IGNORECASE,
)
_OFFSET = re.compile(r"UTC\s*([+-])(\d{1,2}):?(\d{2})\b", re.IGNORECASE)


def confirmed_booking_arguments(message: str) -> dict | None:
    """Accept only a bounded English confirmation with name, E.164 phone and zoned time.

    Other natural-language requests stay on the conversational path. A failed
    parse never authorizes a calendar write.
    """
    if not (_CONFIRM.search(message) and _SAVE.search(message)) or _NEGATE.search(message):
        return None
    name = _NAME.search(message)
    phone = _PHONE.search(message)
    when = _WHEN.search(message)
    offset = _OFFSET.search(message)
    if not all((name, phone, when, offset)):
        return None
    sign, hours, minutes = offset.groups()
    hours, minutes = int(hours), int(minutes)
    if hours > 14 or minutes > 59 or (hours == 14 and minutes != 0):
        return None
    tz = timezone(timedelta(minutes=(1 if sign == "+" else -1) * (hours * 60 + minutes)))
    day, month, year, hour, minute, meridian = when.groups()
    try:
        parsed = datetime.strptime(
            f"{day} {month} {year} {hour}:{minute} {meridian.upper()}",
            "%d %B %Y %I:%M %p",
        ).replace(tzinfo=tz)
    except ValueError:
        return None
    customer_name = name.group(1).strip(" .,;:")
    if len(customer_name) < 2 or customer_name.startswith("["):
        return None
    return {
        "customer_name": customer_name,
        "customer_phone": phone.group(),
        "start_time": parsed.isoformat(),
        "confirmed_by_caller": True,
    }
