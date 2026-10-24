"""Direct answers for unambiguous caller turns that require no model or tools."""

import re

END_CALL_TOOL_NAMES = frozenset({"finish_call", "end_call", "close_conversation", "hang_up"})

def has_live_lookup_tools(tools) -> bool:
    """Control-only end-call transitions cannot retrieve caller records."""
    return any(getattr(tool, "name", None) not in END_CALL_TOOL_NAMES for tool in tools)

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
_ORDER_REFERENCE_TOKEN = r"\s+(?=[A-Za-z0-9_-]*[0-9])[A-Za-z0-9_-]{1,40}"
_ORDER_REFERENCE = r"(?:" + _ORDER_REFERENCE_TOKEN + r")?"
# Hindi STT spells identifiers as words (123 -> एक सौ तेईस). A bounded
# Devanagari reference also covers named items, but never another request.
_HINDI_ORDER_REFERENCE = (
    r"(?:" + _ORDER_REFERENCE_TOKEN
    + r"|(?:\s+(?!(?:और|लेकिन|मगर|फिर|रद्द|बदलो|बदलना)(?:\s|$))[\u0900-\u097f]+){1,6})?"
)
_HINDI_ORDER_STATUS = re.compile(
    r"(?:मेरे|मेरा)\s+ऑर्डर" + _HINDI_ORDER_REFERENCE
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


# No order-update action is configured in this workflow. Handle exact address
# changes truthfully instead of making the caller wait for a generic LLM turn.
_HINDI_ORDER_ADDRESS_CHANGE = re.compile(
    r"(?:(?:मुझे|मेरे को|मैं)\s+)?(?:(?:अपने|मेरे)\s+)?ऑर्डर\s+(?:का|के)\s+"
    r"(?:डिलीवरी\s+)?(?:पता|एड्रेस)\s+(?:बदलना|बदलने|अपडेट\s+करना)"
    r"(?:\s+है)?[.!?।\s]*$",
)
_ENGLISH_ORDER_ADDRESS_CHANGE = re.compile(
    r"(?:(?:i|we)\s+(?:need|want|would\s+like)\s+to\s+)?"
    r"(?:change|update)\s+(?:"
    r"(?:(?:the|my)\s+)?(?:(?:delivery|shipping)\s+)?address\s+"
    r"(?:(?:for|on|of)\s+)?(?:my\s+)?order|"
    r"(?:my\s+)?order\s+(?:(?:delivery|shipping)\s+)?address"
    r")[.!?\s]*$",
    re.IGNORECASE,
)
_ROMAN_HINDI_ORDER_ADDRESS_CHANGE = re.compile(
    r"(?:(?:mujhe|mereko|main|mera)\s+)?(?:(?:apne|mere)\s+)?order\s+(?:(?:ka|ke)\s+)?"
    r"(?:(?:delivery|shipping)\s+)?(?:pata|address)\s+"
    r"(?:badalna|badalne|change\s+karna|update\s+karna)"
    r"(?:\s+(?:hai|he))?[.!?\s]*$",
    re.IGNORECASE,
)

# A no-tool workflow cannot look up an order. Answer clear delivery-delay
# reports without asking an unrelated department question or inventing status.
_HINDI_ORDER_DELIVERY_DELAY = re.compile(
    r"(?:(?:मेरे|मेरा|मेरी)\s+)?ऑर्डर\s+(?:की\s+)?डिलीवरी\s+(?:में\s+)?"
    r"(?:देरी|देर)\s+(?:हो\s+रही|हुई|है|होगी)(?:\s+है)?[.!?।\s]*$",
)
_ENGLISH_ORDER_DELIVERY_DELAY = re.compile(
    r"(?:(?:my|the)\s+)?(?:order|package|parcel)\s+"
    r"(?:(?:delivery|shipment)\s+)?(?:is\s+)?(?:late|delayed|overdue)"
    r"(?:\s+(?:again|today|right\s+now))?[.!?\s]*$",
    re.IGNORECASE,
)
_ROMAN_HINDI_ORDER_DELIVERY_DELAY = re.compile(
    r"(?:(?:mera|mere|meri)\s+)?(?:order|parcel)\s+(?:ki\s+)?delivery\s+"
    r"(?:(?:mein|me)\s+)?(?:der|dair|late)\s+"
    r"(?:(?:ho\s+r(?:ahi|ahi)|hai|he|hoti)\s*(?:hai|he)?)?[.!?\s]*$",
    re.IGNORECASE,
)
_ORDER_DELAY_NEGATION = re.compile(
    r"\b(?:not|never|isn't|wasn't|isnt|wasnt)\b|नहीं|नही|मत|"
    r"\b(?:nahi|nahin|mat)\b",
    re.IGNORECASE,
)

# A no-tool node cannot save an appointment. Handle only a standalone,
# explicit booking request; a route/tool or a combined intent stays with the
# workflow so it can reach the correct configured agent.
_HINDI_UNAVAILABLE_BOOKING = re.compile(
    r"(?:मुझे|हमें|मेरे लिए)\s+(?:(?:आज|कल|परसों)\s+)?(?:एक\s+)?"
    r"(?:अपॉइंटमेंट|बुकिंग)\s+(?:बुक|शेड्यूल)\s+"
    r"(?:करनी|करना|करानी|कराना|चाहिए)(?:\s+है)?[.!?।\s]*$",
)
_ENGLISH_UNAVAILABLE_BOOKING = re.compile(
    r"(?:i|we)\s+(?:want|need|would\s+like)\s+to\s+"
    r"(?:book|schedule)\s+(?:an?\s+)?(?:appointment|consultation)"
    r"(?:\s+(?:for\s+)?(?:today|tomorrow))?[.!?\s]*$",
    re.IGNORECASE,
)
_ROMAN_HINDI_UNAVAILABLE_BOOKING = re.compile(
    r"(?:mujhe|hume)\s+(?:(?:aaj|kal)\s+)?(?:ek\s+)?"
    r"(?:appointment|booking)\s+(?:book|schedule)\s+"
    r"(?:karni|karna|karani|karana)(?:\s+(?:hai|he))?[.!?\s]*$",
    re.IGNORECASE,
)


_HINDI_ROOM_BOOKING = re.compile(
    r"(?:(?:अः|अह|उम्)\s+)?(?:मुझे|मेरे को|हमको|हमें|मेरे लिए|मैं)\s+(?:ना\s+)?(?:एक\s+)?"
    r"(?:(?:रूम|कमरा|कमरे)(?:\s+वगैरह)?(?:\s+की)?\s+(?:बुकिंग|बुक|आरक्षित|रिज़र्व)|"
    r"(?:बुक|बुकिंग|आरक्षित|रिज़र्व)\s+(?:एक\s+)?(?:रूम|कमरा|कमरे))\s+"
    r"(?:करना|करनी|कराना|करानी|करें|करिए|करूँ|चाहिए)(?:\s+है)?"
    r"(?:\s+.+)?[.!?।\s]*$",
)
_ENGLISH_ROOM_BOOKING = re.compile(
    r"(?:(?:i|we)\s+(?:want|need|would\s+like|have)\s+to\s+)?"
    r"(?:book|reserve)\s+(?:a\s+|the\s+|my\s+)?(?:hotel\s+)?room"
    r"(?:\s+.+)?[.!?\s]*$",
    re.IGNORECASE,
)
_ROMAN_HINDI_ROOM_BOOKING = re.compile(
    r"(?:(?:mujhe|mere\s+liye|humko)\s+)?(?:ek\s+)?"
    r"(?:room|kamra|kamre)\s+(?:book|reserve|booking)\s+"
    r"(?:karna|karni|karana|karani)(?:\s+(?:hai|he))?"
    r"(?:\s+.+)?[.!?\s]*$",
    re.IGNORECASE,
)
_ROOM_BOOKING_NEGATION = re.compile(
    r"\b(?:don't|do\s+not|not|cancel|stop|no\s+longer)\b|नहीं|नही|मत|\b(?:nahi|nahin|mat)\b",
    re.IGNORECASE,
)

_HINDI_ORDER_ENQUIRY = re.compile(
    r"(?:(?:अः|अं|उम्)[,،]?\s+)?(?:मुझे|हमको|हमें)\s+"
    r"(?:(?:एक|अपने)\s+)?ऑर्डर\b"
    r"(?:\s+[\w\u0900-\u097f]+){0,6}\s+बात\s+कर(?:नी|ना)?"
    r"(?!\s*(?:नहीं|मत))\s*(?:है|थी|था)?"
    r"[.!?।\s]*$",
)
_ENGLISH_ORDER_ENQUIRY = re.compile(
    r"(?:i|we)\s+(?:want|need|would\s+like)\s+to\s+(?:talk|speak)\s+"
    r"(?:to\s+(?:you|someone)\s+)?about\s+(?:an?\s+|my\s+)?order[.!?\s]*$",
    re.IGNORECASE,
)

_HINDI_NEW_ORDER_REQUEST = re.compile(
    r"(?:\u092e\u0941\u091d\u0947|\u0939\u092e\u0947\u0902|\u0939\u092e\u0915\u094b)\s+(?:\u090f\u0915\s+)?(?:\u0928\u092f\u093e\s+)?\u0911\u0930\u094d\u0921\u0930\s+"
    r"(?:(?:\u092c\u0941\u0915|\u092a\u094d\u0932\u0947\u0938)\s+)?(?:\u0926\u0947\u0928\u093e|\u0915\u0930\u0928\u093e|\u092c\u0928\u093e\u0928\u093e)\s+(?:\u0939\u0948|\u091a\u093e\u0939\u093f\u090f)[.!?\u0964\s]*$",
)
_ENGLISH_NEW_ORDER_REQUEST = re.compile(
    r"(?:i|we)\s+(?:(?:want|need)\s+to|would\s+like\s+to|'d\s+like\s+to)\s+"
    r"(?:place|make|create)\s+(?:a\s+)?(?:new\s+)?order[.!?\s]*$",
    re.IGNORECASE,
)
_ROMAN_HINDI_NEW_ORDER_REQUEST = re.compile(
    r"(?:mujhe|hume|humko)\s+(?:ek\s+)?(?:naya\s+)?order\s+"
    r"(?:(?:book|place)\s+)?(?:karna|dena|banana)\s+(?:hai|chahiye)[.!?\s]*$",
    re.IGNORECASE,
)



# Exact standalone help requests need only a clarifying question. Answer these
# locally so a slow/unstable small LLM cannot repeat its previous fallback.
# Permit one common hesitation prefix, while fullmatch keeps added intent on
# the normal model/tool path.
_HESITATION_PREFIX = (
    r"(?:(?:हम्म|ह्म्म|अच्छा|जी|हाँ|हां|अं|अः|उम्|hmm|umm|um|uh|well|okay|ok|haan|acha)"
    r"[,،]?\s+)?"
)
_HINDI_HELP_REQUEST = re.compile(
    _HESITATION_PREFIX +
    r"(?:मुझे|हमें|हमको)\s+(?:(?:एक|कुछ)\s+)?(?:मदद|सहायता|हेल्प)\s+"
    r"(?:चाहिए|चाह|रह)(?:\s+(?:है|था|थी))?[.!?।\s]*$",
)
_HINDI_INFO_REQUEST = re.compile(
    _HESITATION_PREFIX +
    r"(?:मुझे|हमें|हमको)\s+(?:(?:एक|कुछ)\s+)?जानकारी\s+"
    r"चाहिए(?:\s+(?:है|था|थी))?[.!?।\s]*$",
)
_ENGLISH_HELP_REQUEST = re.compile(
    _HESITATION_PREFIX +
    r"(?:i|we)\s+(?:(?:just|only)\s+)?(?:need|want|wanted)\s+"
    r"(?:(?:some|a\s+bit\s+of)\s+)?(?:help|assistance|information)"
    r"(?:\s+please)?[.!?\s]*$",
    re.IGNORECASE,
)
_ROMAN_HINDI_HELP_REQUEST = re.compile(
    _HESITATION_PREFIX +
    r"(?:mujhe|hume|humko)\s+(?:(?:ek|kuch|thodi)\s+)?"
    r"(?:madad|sahayata|help|information)\s+chahiye"
    r"(?:\s+(?:hai|tha|thi))?[.!?\s]*$",
    re.IGNORECASE,
)


def direct_caller_reply(text: str, *, has_lookup_tools: bool) -> str | None:
    """Skip inference only for exact, capability-safe caller requests.

    A vague request to discuss an order gets a clarification even when the
    workflow has tools. Explicit order status requests stay on the tool path.
    Multi-intent messages are left to the normal workflow.
    """
    if _HINDI_BOOKING_REFUSAL.fullmatch(text):
        return "ठीक है, कोई बात नहीं।"
    if _ENGLISH_BOOKING_REFUSAL.fullmatch(text):
        return "Okay, no problem."
    if _ROMAN_HINDI_BOOKING_REFUSAL.fullmatch(text):
        return "ठीक है, कोई बात नहीं।"
    if _HINDI_HELP_REQUEST.fullmatch(text) or _ROMAN_HINDI_HELP_REQUEST.fullmatch(text):
        return "ज़रूर, किस काम में मदद चाहिए?"
    if _HINDI_INFO_REQUEST.fullmatch(text):
        return "ज़रूर, किस बारे में जानकारी चाहिए?"
    if _ENGLISH_HELP_REQUEST.fullmatch(text):
        return "Sure, what do you need help with?"
    if _HINDI_ORDER_ENQUIRY.fullmatch(text):
        return "ज़रूर, ऑर्डर में क्या मदद चाहिए?"
    if _ENGLISH_ORDER_ENQUIRY.fullmatch(text):
        return "Sure, what do you need help with on the order?"
    if not has_lookup_tools:
        if not _ROOM_BOOKING_NEGATION.search(text):
            if _HINDI_ROOM_BOOKING.fullmatch(text):
                return "माफ़ कीजिए, मैं यहाँ कमरे की उपलब्धता या बुकिंग की पुष्टि नहीं कर सकती। कृपया सहायता टीम से संपर्क करें।"
            if _ENGLISH_ROOM_BOOKING.fullmatch(text):
                return "Sorry, I can’t check room availability or make a booking here. Please contact the support team."
            if _ROMAN_HINDI_ROOM_BOOKING.fullmatch(text):
                return "माफ़ कीजिए, मैं यहाँ कमरे की उपलब्धता या बुकिंग की पुष्टि नहीं कर सकती। कृपया सहायता टीम से संपर्क करें।"
        if _HINDI_UNAVAILABLE_BOOKING.fullmatch(text):
            return "माफ़ कीजिए, यहाँ अपॉइंटमेंट बुक करने की सुविधा जुड़ी नहीं है। कृपया आधिकारिक सपोर्ट से बुकिंग करें।"
        if _ENGLISH_UNAVAILABLE_BOOKING.fullmatch(text):
            return "I can't book an appointment here yet. Please contact the official support team to arrange it."
        if _ROMAN_HINDI_UNAVAILABLE_BOOKING.fullmatch(text):
            return "माफ़ कीजिए, यहाँ अपॉइंटमेंट बुक करने की सुविधा जुड़ी नहीं है। कृपया आधिकारिक सपोर्ट से बुकिंग करें।"
        if _HINDI_NEW_ORDER_REQUEST.fullmatch(text):
            return "\u091c\u093c\u0930\u0942\u0930, \u0906\u092a \u0915\u094d\u092f\u093e \u0911\u0930\u094d\u0921\u0930 \u0915\u0930\u0928\u093e \u091a\u093e\u0939\u0947\u0902\u0917\u0947?"
        if _ENGLISH_NEW_ORDER_REQUEST.fullmatch(text):
            return "Sure, what would you like to order?"
        if _ROMAN_HINDI_NEW_ORDER_REQUEST.fullmatch(text):
            return "Bilkul, aap kya order karna chahenge?"
        if _HINDI_ORDER_STATUS.fullmatch(text):
            return "माफ़ कीजिए, मुझे लाइव ऑर्डर की जानकारी नहीं दिखती। कृपया आधिकारिक सपोर्ट से संपर्क करें।"
        if _ENGLISH_ORDER_STATUS.fullmatch(text):
            return "I can't see live order details. Please contact our support team for an update."
        if _ROMAN_HINDI_ORDER_STATUS.fullmatch(text):
            return "मुझे लाइव ऑर्डर की जानकारी नहीं दिखती। कृपया आधिकारिक सपोर्ट से संपर्क करें।"
        if _HINDI_ORDER_ADDRESS_CHANGE.fullmatch(text):
            return (
                "माफ़ कीजिए, इस कॉल में ऑर्डर का पता बदलने की सुविधा जुड़ी नहीं है। "
                "कृपया अपने ऑर्डर पेज से पता अपडेट करें या सपोर्ट से संपर्क करें।"
            )
        if _ENGLISH_ORDER_ADDRESS_CHANGE.fullmatch(text):
            return (
                "I can't change an order address in this call. Please update it from "
                "your order page or contact support."
            )
        if _ROMAN_HINDI_ORDER_ADDRESS_CHANGE.fullmatch(text):
            return (
                "माफ़ कीजिए, इस कॉल में ऑर्डर का पता बदलने की सुविधा जुड़ी नहीं है। "
                "कृपया अपने ऑर्डर पेज से पता अपडेट करें या सपोर्ट से संपर्क करें।"
            )
        if not _ORDER_DELAY_NEGATION.search(text):
            if _HINDI_ORDER_DELIVERY_DELAY.fullmatch(text):
                return "माफ़ कीजिए, मुझे लाइव डिलीवरी स्टेटस नहीं दिखता। कृपया आधिकारिक ट्रैकिंग लिंक या सपोर्ट से जानकारी लें।"
            if _ENGLISH_ORDER_DELIVERY_DELAY.fullmatch(text):
                return "I can't see live delivery updates here. Please use your official tracking link or contact support."
            if _ROMAN_HINDI_ORDER_DELIVERY_DELAY.fullmatch(text):
                return "माफ़ कीजिए, मुझे लाइव डिलीवरी स्टेटस नहीं दिखता। कृपया आधिकारिक ट्रैकिंग लिंक या सपोर्ट से जानकारी लें।"
    return None
