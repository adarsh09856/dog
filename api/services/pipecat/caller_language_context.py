"""Stable, request-only language hints for a single conversation's LLM."""

import re

from api.services.configuration.language_normalizer import (
    SPEECH_LANGUAGE_NAMES,
    normalize_language_code,
)


_ENGLISH_SWITCH = re.compile(
    r"(?:\b(?:speak|talk|reply|answer|continue|switch)\b.{0,36}\b(?:in|to)\s+english\b|"
    r"\benglish\s+(?:please|mein|me|main)\b|"
    r"(?:इंग्लिश|अंग्रेज़ी|अंग्रेजी)\s+में\s+(?:बात|बोल|जवाब|उत्तर)|"
    r"(?:बात|बोल|जवाब|उत्तर).{0,24}(?:इंग्लिश|अंग्रेज़ी|अंग्रेजी)\s+में|"
    r"(?:इंग्लिश|अंग्रेज़ी|अंग्रेजी)\s+में\s+बात\s+कर\s+सकत)",
    re.IGNORECASE,
)
_HINDI_SWITCH = re.compile(
    r"(?:\b(?:speak|talk|reply|answer|continue|switch)\b.{0,36}\b(?:in|to)\s+hindi\b|"
    r"\bhindi\s+(?:please|mein|me|main)\b|"
    r"हिंदी\s+में\s+(?:बात|बोल|जवाब|उत्तर)|"
    r"(?:बात|बोल|जवाब|उत्तर).{0,24}हिंदी\s+में)",
    re.IGNORECASE,
)
_STANDALONE_ENGLISH_REQUEST = re.compile(
    r"\s*(?:(?:अः|अह|uh|um|please|कृपया)\s+)?(?:"
    r"(?:can|could|would)\s+you\s+(?:please\s+)?(?:speak|talk|reply|answer|continue)"
    r"(?:\s+to\s+me)?\s+(?:in\s+)?english|"
    r"(?:कन|कैन)\s*यू\s*(?:टॉक|टाक|ताार्क|स्पीक)\s+(?:इन\s+)?इंग्लिश|"
    r"(?:क्या\s+)?(?:तुम|आप)\s+(?:इंग्लिश|अंग्रेज़ी|अंग्रेजी)\s+में\s+"
    r"(?:(?:बात|प)\s+)?(?:कर\s+सकत[ेी]\s+(?:हो|हैं)|बोल\s+सकत[ेी]\s+(?:हो|हैं))|"
    r"(?:अब\s+)?(?:इंग्लिश|अंग्रेज़ी|अंग्रेजी)\s+में\s+"
    r"(?:बोलिए|बोलो|बताइए|जवाब\s+दें|बात\s+(?:करो|करें|करिए|कीजिए))|"
    r"(?:switch|continue|reply|answer|speak|talk)\s+(?:in|to)\s+english|english\s+please"
    r")(?:\s+please)?[.?!।\s]*",
    re.IGNORECASE,
)
_STANDALONE_HINDI_REQUEST = re.compile(
    r"\s*(?:(?:please|कृपया|अब)\s+)?(?:"
    r"(?:can|could|would)\s+you\s+(?:please\s+)?(?:speak|talk|reply|answer|continue)"
    r"(?:\s+to\s+me)?\s+(?:in\s+)?hindi|"
    r"(?:switch|continue|reply|answer|speak|talk)\s+(?:in|to)\s+hindi|hindi\s+please|"
    r"हिंदी\s+में\s+(?:बोलिए|बोलो|बताइए|जवाब\s+दें|बात\s+करो)"
    r")[.?!।\s]*",
    re.IGNORECASE,
)


_LANGUAGE_SWITCH_VERBS = r"(?:speak|talk|reply|answer|continue|switch)"
_LANGUAGE_REQUEST_WRAPPERS = r"(?:can|could|would)\s+you\s+(?:please\s+)?"
_LANGUAGE_NAME_ALIASES = {"Odia": ("Odia", "Oriya")}


def _supported_language_codes(supported_languages=None) -> frozenset[str]:
    """Return the reply-language capability set for this agent visit.

    ``None`` keeps the legacy Hindi/English behavior for callers that do not
    have a TTS capability descriptor (for example text-only helpers). An
    explicit empty set means this visit has no verified language-switching
    capability.
    """
    if supported_languages is None:
        return frozenset({"en", "hi"})
    result = set()
    for language in supported_languages:
        code = normalize_language_code(str(language))
        if code in SPEECH_LANGUAGE_NAMES:
            result.add(code)
    return frozenset(result)


def reply_language_switch_capabilities(supported_languages, source=None) -> frozenset[str]:
    """Intersect TTS routing with the active recognizer's switch capability.

    Auto STT remains auto-detected and keeps the TTS capability set. A fixed
    recognizer without an in-call language selector can only receive input in
    its configured language. Selectable recognizers validate non-auto targets
    asynchronously before the caller's override is persisted.
    """
    codes = _supported_language_codes(supported_languages)
    if source is None:
        return codes
    settings = getattr(source, "_settings", None)
    language = getattr(settings, "language", None)
    if language is None or str(getattr(language, "value", language)).strip().casefold() in {
        "", "auto", "multi", "multilingual", "unknown", "default", "none",
    }:
        return codes
    if callable(getattr(source, "select_caller_language", None)):
        return codes
    current = normalize_language_code(str(getattr(language, "value", language)))
    return codes.intersection({current})


def _language_names(supported_languages=None) -> dict[str, str]:
    codes = _supported_language_codes(supported_languages)
    names = {}
    for code in codes:
        name = SPEECH_LANGUAGE_NAMES[code]
        names[name.casefold()] = name
        for alias in _LANGUAGE_NAME_ALIASES.get(name, ()):
            names[alias.casefold()] = name
    return names


def _generic_language_request(text: str, supported_languages=None) -> str | None:
    """Recognize an explicit switch only to languages this TTS can emit."""
    names = _language_names(supported_languages)
    if not names:
        return None
    target = "(?P<language>" + "|".join(
        re.escape(name) for name in sorted(names, key=len, reverse=True)
    ) + ")"
    patterns = (
        re.compile(
            rf"\b{_LANGUAGE_REQUEST_WRAPPERS}{_LANGUAGE_SWITCH_VERBS}"
            rf"(?:\s+to\s+me)?\s+(?:(?:in|to)\s+)?{target}\b",
            re.IGNORECASE,
        ),
        re.compile(
            rf"\b{_LANGUAGE_SWITCH_VERBS}\s+(?:in|to)\s+{target}\b",
            re.IGNORECASE,
        ),
        re.compile(rf"\b{target}\s+(?:please|mein|me|main)\b", re.IGNORECASE),
    )
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return names[match.group("language").casefold()]
    # Keep the existing Hindi-recognizer tolerance for explicit English/Hindi
    # requests while allowing every configured language name above.
    if "hi" in _supported_language_codes(supported_languages):
        if _ENGLISH_SWITCH.search(text):
            return "English"
        if _HINDI_SWITCH.search(text):
            return "Hindi"
    return None


def _trusted_detected_language(source) -> str | None:
    """Use the voice router's confidence-filtered language when available.

    A present-but-empty ``latest_tts_language`` is intentional: the detector
    heard a weak or unsupported label, so it must not steer the reply language.
    Older recognizers do not expose that property and retain the legacy raw
    detected-language behavior.
    """
    if source is None:
        return None
    if hasattr(source, "latest_tts_language"):
        return getattr(source, "latest_tts_language", None)
    return getattr(source, "latest_detected_language", None)


def sync_contact_reply_language(state: dict, source) -> None:
    """Keep deterministic contact follow-ups aligned with the live voice route.

    Explicit language choices take precedence while active. When auto routing
    resumes, a confidence-filtered language may replace the stored
    contact-flow language; weak/unknown labels clear a
    stale choice rather than pinning later phone/date prompts to it.
    """
    if not isinstance(state, dict) or source is None:
        return

    language = getattr(source, "reply_language_override", None)
    if language is None:
        language = _trusted_detected_language(source)
    raw_language = getattr(language, "value", language)
    code = normalize_language_code(raw_language) if raw_language is not None else ""
    if code in SPEECH_LANGUAGE_NAMES:
        state["reply_language"] = SPEECH_LANGUAGE_NAMES[code]
    else:
        state.pop("reply_language", None)


def standalone_language_request(text: str, supported_languages=None) -> str | None:
    """A reply-language setting request with no other task to drop."""
    names = _language_names(supported_languages)
    if not names:
        return None
    for alias, display in sorted(names.items(), key=lambda item: len(item[0]), reverse=True):
        escaped = re.escape(alias)
        if re.fullmatch(
            rf"\s*(?:(?:please|कृपया|अः|अह|uh|um)\s+)?"
            rf"(?:(?:can|could|would)\s+you\s+(?:please\s+)?)?"
            rf"(?:{_LANGUAGE_SWITCH_VERBS})(?:\s+to\s+me)?\s+"
            rf"(?:(?:in|to)\s+)?{escaped}(?:\s+please)?[.?!।\s]*",
            text,
            re.IGNORECASE,
        ) or re.fullmatch(
            rf"\s*(?:{escaped})\s+(?:please|mein|me|main)[.?!।\s]*",
            text,
            re.IGNORECASE,
        ):
            return display
    if "en" in _supported_language_codes(supported_languages) and _STANDALONE_ENGLISH_REQUEST.fullmatch(text):
        return "English"
    if "hi" in _supported_language_codes(supported_languages) and _STANDALONE_HINDI_REQUEST.fullmatch(text):
        return "Hindi"
    return None


def _requested_language(text: str, supported_languages=None) -> str | None:
    """Recognize an explicit reply-language request, even in another language."""
    standalone = standalone_language_request(text, supported_languages)
    if standalone:
        return standalone
    return _generic_language_request(text, supported_languages)


class CallerLanguageContext:
    def __init__(self):
        self._hints: dict[tuple[int, str], str] = {}
        self._explicit_preference: str | None = None
        self._explicit_source_language: str | None = None
        self._explicit_target_language: str | None = None

    def choose_language(self, language: str, source=None, *, text: str = "") -> None:
        # Keep the transcript's raw STT result intact, but guide the LLM with
        # the language that the active TTS inventory can actually speak.
        detected = _trusted_detected_language(source)
        code = str(detected or "").lower().replace("_", "-").split("-", 1)[0]
        spoken = SPEECH_LANGUAGE_NAMES.get(code)
        if not spoken:
            spoken = "Hindi" if re.search(r"[\u0900-\u097f]", text) else "English"
        code = normalize_language_code(language)
        self._explicit_preference = SPEECH_LANGUAGE_NAMES.get(code, language)
        self._explicit_target_language = code
        self._explicit_source_language = spoken

    def apply(self, messages: list, source, supported_languages=None) -> list:
        """Keep earlier utterances identical as a caller changes language.

        The STT source describes only its latest recognition. Remember the
        associated hint while that utterance remains in the context, rather
        than stripping it on the following turn and invalidating the model's
        cached prefix. The engine shares this state across LLM services within
        one call so an agent handoff does not forget the caller's choice. It is
        never a process-global cache and does not modify supplied dictionaries.
        """
        has_supported_language_inventory = supported_languages is not None
        supported_languages = reply_language_switch_capabilities(
            supported_languages, source
        )
        users = [
            (index, message["content"])
            for index, message in enumerate(messages)
            if isinstance(message, dict)
            and message.get("role") == "user"
            and isinstance(message.get("content"), str)
        ]
        keys = {(ordinal, text) for ordinal, (_, text) in enumerate(users)}
        self._hints = {key: hint for key, hint in self._hints.items() if key in keys}
        if not users:
            self._explicit_preference = None
            self._explicit_source_language = None
            self._explicit_target_language = None

        # A new agent may use a TTS model with a narrower verified inventory.
        # Drop an inherited preference the active voice cannot produce so the
        # LLM text and synthesized language do not diverge after a handoff.
        supported_codes = _supported_language_codes(supported_languages)
        if (
            self._explicit_preference
            and normalize_language_code(self._explicit_preference) not in supported_codes
        ):
            self._explicit_preference = None
            self._explicit_source_language = None
            self._explicit_target_language = None

        # Text chat creates a new service for each turn and has no STT source.
        # Recover explicit choices from its persisted caller history so a
        # successful switch acknowledgment also governs subsequent replies.
        if source is None:
            # Text chat has no recognizer metadata. Reuse the conservative
            # English classifier used by the local LLM adapter; avoid assigning
            # English to Romanized Hindi or mixed Indic-script text.
            from api.services.pipecat.booking_tool_choice import _clearly_english_caller_text

            for ordinal, (_, text) in enumerate(users):
                requested = standalone_language_request(text, supported_languages)
                if requested:
                    self._explicit_preference = requested
                    self._explicit_target_language = normalize_language_code(requested)
                if self._explicit_preference:
                    self._hints.setdefault((ordinal, text), (
                        f"Caller explicitly chose {self._explicit_preference}. "
                        f"Reply only in {self._explicit_preference}; do not repeat "
                        "answered questions."
                    ))
                elif _clearly_english_caller_text(text):
                    self._hints.setdefault((ordinal, text), (
                        "Reply in English; do not repeat answered questions."
                    ))

        # STT can identify languages beyond the installed TTS inventory. Keep
        # the raw detector metadata, but reply in a voice we can actually emit.
        detected = _trusted_detected_language(source)
        detected_text = getattr(source, "latest_detected_text", None)
        latest_user_text = users[-1][1] if users else ""
        explicit_language = (
            _requested_language(latest_user_text, supported_languages) if users else None
        )
        if explicit_language:
            self._explicit_preference = explicit_language
            self._explicit_target_language = normalize_language_code(explicit_language)
            # A low-confidence detector may intentionally expose no TTS
            # language. Still honor the caller's explicit reply-language
            # request, while tracking the utterance's likely source language
            # separately so a later language change can resume auto mode.
            if not detected:
                detected = "hi" if re.search(r"[\u0900-\u097f]", latest_user_text) else "en"
                detected_text = latest_user_text
        if (
            users and users[-1][0] == len(messages) - 1
            and isinstance(detected, str)
            and isinstance(detected_text, str) and detected_text.strip()
            and detected_text.casefold() in users[-1][1].casefold()
        ):
            code = detected.strip().lower().replace("_", "-").split("-", 1)[0]
            language = SPEECH_LANGUAGE_NAMES.get(code)
            key = (len(users) - 1, users[-1][1])
            if (
                language
                and (not has_supported_language_inventory or code in supported_codes)
                and key not in self._hints
            ):
                requested = explicit_language or _requested_language(
                    users[-1][1], supported_languages
                )
                if requested:
                    self._explicit_preference = requested
                    self._explicit_source_language = language
                    self._explicit_target_language = normalize_language_code(requested)
                elif (
                    self._explicit_source_language != language
                    and self._explicit_target_language != code
                ):
                    # A later utterance in another language resumes automatic
                    # matching without rewriting any earlier request hints. A
                    # caller may also start using their explicitly requested
                    # reply language; that must not cancel their preference.
                    self._explicit_preference = None
                    self._explicit_source_language = None
                    self._explicit_target_language = None
                answer_language = self._explicit_preference or language
                if self._explicit_preference and answer_language != language:
                    self._hints[key] = (
                        f"Caller explicitly chose {answer_language}. Reply only in "
                        f"{answer_language}, even if speaking {language}. Do not greet "
                        "or repeat answered questions."
                    )
                else:
                    self._hints[key] = (
                        f"Answer in {answer_language} with natural grammar. No "
                        "translation unless asked; do not repeat the greeting."
                    )

        # The same preference that guides the LLM must guide TTS. Otherwise
        # an explicit "speak English" request can produce English text while
        # the speech service still uses the previous Hindi detector result.
        # Keep this override call-scoped on the recognizer and clear it as
        # soon as a later utterance changes the detected source language.
        if source is not None:
            source.reply_language_override = (
                normalize_language_code(self._explicit_preference)
                if self._explicit_preference
                and normalize_language_code(self._explicit_preference)
                in _supported_language_codes(supported_languages)
                else None
            )

        result = list(messages)
        for ordinal, (index, content) in enumerate(users):
            hint = self._hints.get((ordinal, content))
            if hint:
                result[index] = {
                    **messages[index], "content": f"[{hint}]\n{content}",
                }
        return result
