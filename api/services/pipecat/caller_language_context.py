"""Stable, request-only language hints for a single conversation's LLM."""

import re

from api.services.configuration.language_normalizer import SPEECH_LANGUAGE_NAMES


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


def _requested_language(text: str) -> str | None:
    """Recognize an explicit reply-language request, even in another language."""
    english = _ENGLISH_SWITCH.search(text)
    hindi = _HINDI_SWITCH.search(text)
    if english and hindi:
        return "English" if english.start() > hindi.start() else "Hindi"
    if english:
        return "English"
    if hindi:
        return "Hindi"
    return None


class CallerLanguageContext:
    def __init__(self):
        self._hints: dict[tuple[int, str], str] = {}
        self._explicit_preference: str | None = None
        self._explicit_source_language: str | None = None

    def apply(self, messages: list, source) -> list:
        """Keep earlier utterances identical as a caller changes language.

        The STT source describes only its latest recognition. Remember the
        associated hint while that utterance remains in the context, rather
        than stripping it on the following turn and invalidating the model's
        cached prefix. This state belongs to one LLM service, never a global
        cache, and does not modify the transcript or supplied dictionaries.
        """
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

        detected = getattr(source, "latest_detected_language", None)
        detected_text = getattr(source, "latest_detected_text", None)
        if (
            users and users[-1][0] == len(messages) - 1
            and isinstance(detected, str)
            and isinstance(detected_text, str) and detected_text.strip()
            and detected_text.casefold() in users[-1][1].casefold()
        ):
            code = detected.strip().lower().replace("_", "-").split("-", 1)[0]
            language = SPEECH_LANGUAGE_NAMES.get(code)
            key = (len(users) - 1, users[-1][1])
            if language and key not in self._hints:
                requested = _requested_language(users[-1][1])
                if requested:
                    self._explicit_preference = requested
                    self._explicit_source_language = language
                elif self._explicit_source_language != language:
                    # A later utterance in another language resumes automatic
                    # matching without rewriting any earlier request hints.
                    self._explicit_preference = None
                    self._explicit_source_language = None
                answer_language = self._explicit_preference or language
                if self._explicit_preference and answer_language != language:
                    self._hints[key] = (
                        f"The caller just spoke {language}, but explicitly chose "
                        f"{answer_language} for assistant replies. This choice is still "
                        f"active. Reply only in {answer_language}, even if the caller "
                        f"speaks {language}. An earlier default language in the agent "
                        "prompt applies only until the caller asks to switch. Do not "
                        "repeat questions the caller has already answered."
                    )
                else:
                    self._hints[key] = (
                        f"The caller just spoke {language}. Answer in {answer_language}; "
                        "follow their latest language choice and do not repeat the greeting."
                    )

        result = list(messages)
        for ordinal, (index, content) in enumerate(users):
            hint = self._hints.get((ordinal, content))
            if hint:
                result[index] = {
                    **messages[index], "content": f"[{hint}]\n{content}",
                }
        return result
