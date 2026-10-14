"""Require the calendar action when a caller explicitly confirms a booking."""

import re

from pipecat.services.kodewaves.llm import KodewavesLLMService
from pipecat.services.openai.llm import OpenAILLMService

_CONFIRMATION = re.compile(r"\b(confirm(?:ed)?|save|proceed|book it)\b|पुष्टि|पक्क[ाी]|सेव", re.IGNORECASE)
_BOOKING = re.compile(r"\b(appointment|booking|consultation|reservation)\b|अपॉइंटमेंट|बुकिंग|नियुक्ति", re.IGNORECASE)
_NEGATION = re.compile(r"\b(don't|do not|not now|cancel|stop|never|no,?\s)\b|मत\s|नहीं", re.IGNORECASE)


def _message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def booking_tool_choice(params: dict) -> dict | None:
    """Return a forced function choice only for an unambiguous caller request."""
    tools = params.get("tools")
    messages = params.get("messages")
    if not isinstance(tools, list) or not isinstance(messages, list) or not messages:
        return None
    if not any(
        isinstance(tool, dict)
        and tool.get("type") == "function"
        and tool.get("function", {}).get("name") == "book_appointment"
        for tool in tools
    ):
        return None
    last = messages[-1]
    if not isinstance(last, dict) or last.get("role") != "user":
        return None
    caller_text = _message_text(last)
    if not _CONFIRMATION.search(caller_text) or _NEGATION.search(caller_text):
        return None
    recent_dialogue = " ".join(
        _message_text(message)
        for message in messages[-5:]
        if isinstance(message, dict) and message.get("role") in ("user", "assistant")
    )
    if not _BOOKING.search(recent_dialogue):
        return None
    return {"type": "function", "function": {"name": "book_appointment"}}


class _BookingToolChoiceMixin:
    def build_chat_completion_params(self, params_from_context):
        params = super().build_chat_completion_params(params_from_context)
        choice = booking_tool_choice(params)
        if choice:
            params["tool_choice"] = choice
        return params


class BookingOpenAILLMService(_BookingToolChoiceMixin, OpenAILLMService):
    """OpenAI-compatible provider with confirmed-booking action enforcement."""


class BookingKodewavesLLMService(_BookingToolChoiceMixin, KodewavesLLMService):
    """Sovereign Ollama provider with confirmed-booking action enforcement."""
