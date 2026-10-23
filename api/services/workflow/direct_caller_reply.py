"""Direct answers for unambiguous caller turns that require no model or tools."""

import re

_HINDI_BOOKING_REFUSAL = re.compile(
    r"(?:(?:रुकिए|रोकिए|नहीं)[,،]?\s*)?(?:मुझे|हमें)\s+(?:अब\s+)?"
    r"(?:बुकिंग|अपॉइंटमेंट)\s+"
    r"(?:नहीं\s+(?:करनी|चाहिए)|मत\s+कीजिए)\s*"
    r"(?:है|करनी)?[.!।\s]*$",
)
_ENGLISH_BOOKING_REFUSAL = re.compile(
    r"(?:(?:wait|no)[, ]+)?(?:i|we)\s+"
    r"(?:(?:do\s+not|don't|no\s+longer)\s+(?:want|need)\s+(?:to\s+)?"
    r"(?:book|schedule)(?:\s+(?:an?\s+)?appointment)?|"
    r"(?:do\s+not|don't)\s+(?:book|schedule)(?:\s+(?:an?\s+)?appointment)?|"
    r"(?:do\s+not|don't)\s+(?:want|need)\s+(?:an?\s+)?appointment)"
    r"[.!?\s]*$",
    re.IGNORECASE,
)
_ROMAN_HINDI_BOOKING_REFUSAL = re.compile(
    r"(?:rukiye[, ]+)?(?:mujhe|hume)\s+"
    r"(?:booking|appointment)\s+(?:nahi|nahin)\s+karni\s+(?:hai)?[.!?\s]*$",
    re.IGNORECASE,
)
# Restrict optional references to one bounded identifier containing a digit.
# This must not consume another intent, such as "and change its address".
_ORDER_REFERENCE = r"(?:\s+(?=[A-Za-z0-9_-]*[0-9])[A-Za-z0-9_-]{1,40})?"
_HINDI_ORDER_STATUS = re.compile(
    r"(?:मेरे|मेरा)\s+ऑर्डर" + _ORDER_REFERENCE
    + r"\s+(?:का\s+क्या\s+हुआ|(?:की\s+)?(?:स्थिति|स्टेटस)\s+क्या\s+है|कहाँ\s+है)\s*[?।!\s]*$",
)
_ENGLISH_ORDER_STATUS = re.compile(
    r"(?:what(?:'s|\s+is)\s+the\s+status\s+of\s+my\s+order|"
    r"where\s+is\s+my\s+order)" + _ORDER_REFERENCE + r"[?!.\s]*$",
    re.IGNORECASE,
)
_ROMAN_HINDI_ORDER_STATUS = re.compile(
    r"(?:mera|mere)\s+order" + _ORDER_REFERENCE
    + r"\s+(?:kahan\s+hai|ka\s+kya\s+hua)[?!.\s]*$",
    re.IGNORECASE,
)


def direct_caller_reply(text: str, *, has_lookup_tools: bool) -> str | None:
    """Skip inference only for exact refusal or unavailable live-order requests.

    A multi-intent message is left to the normal workflow, as are order requests
    when tools might have access to live records.
    """
    if _HINDI_BOOKING_REFUSAL.fullmatch(text):
        return "ठीक है, कोई बात नहीं।"
    if _ENGLISH_BOOKING_REFUSAL.fullmatch(text):
        return "Okay, no problem."
    if _ROMAN_HINDI_BOOKING_REFUSAL.fullmatch(text):
        return "ठीक है, कोई बात नहीं।"
    if not has_lookup_tools:
        if _HINDI_ORDER_STATUS.fullmatch(text):
            return "माफ़ कीजिए, मुझे लाइव ऑर्डर की जानकारी नहीं दिखती। कृपया आधिकारिक सपोर्ट से संपर्क करें।"
        if _ENGLISH_ORDER_STATUS.fullmatch(text):
            return "I can't see live order details. Please contact our support team for an update."
        if _ROMAN_HINDI_ORDER_STATUS.fullmatch(text):
            return "मुझे लाइव ऑर्डर की जानकारी नहीं दिखती। कृपया आधिकारिक सपोर्ट से संपर्क करें।"
    return None
