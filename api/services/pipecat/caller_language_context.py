"""Stable, request-only language hints for a single conversation's LLM."""

from api.services.configuration.language_normalizer import SPEECH_LANGUAGE_NAMES


class CallerLanguageContext:
    def __init__(self):
        self._hints: dict[tuple[int, str], str] = {}

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
                self._hints[key] = (
                    f"Reply only in {language}, using natural grammar. "
                    "No translation unless asked; do not repeat the greeting."
                )

        result = list(messages)
        for ordinal, (index, content) in enumerate(users):
            hint = self._hints.get((ordinal, content))
            if hint:
                result[index] = {
                    **messages[index], "content": f"[{hint}]\n{content}",
                }
        return result
