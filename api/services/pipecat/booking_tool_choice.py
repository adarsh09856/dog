"""Require the calendar action when a caller explicitly confirms a booking."""

import re
from loguru import logger
from openai import AsyncOpenAI, DefaultAsyncHttpxClient
from pipecat.frames.frames import LLMFullResponseEndFrame, LLMFullResponseStartFrame

from pipecat.services.kodewaves.llm import KodewavesLLMService
from pipecat.services.openai.llm import OpenAILLMService

_CONFIRMATION = re.compile(r"\b(confirm(?:ed)?|save|proceed|book it)\b|पुष्टि|पक्क[ाी]|सेव", re.IGNORECASE)
_BOOKING = re.compile(r"\b(appointment|booking|consultation|reservation)\b|अपॉइंटमेंट|बुकिंग|नियुक्ति", re.IGNORECASE)
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
_NEGATION = re.compile(r"\b(don't|do not|not now|cancel|stop|never|no,?\s)\b|मत\s|नहीं", re.IGNORECASE)
_OPENING_GREETING = re.compile(
    r"^\s*(?:नमस्ते|नमस्कार|सुप्रभात|शुभ संध्या|namaste|hello|hi|good morning|good afternoon|good evening)",
    re.IGNORECASE,
)
_END_CALL_TOOLS = frozenset(
    {"finish_call", "end_call", "close_conversation", "hang_up"}
)
_EXPLICIT_END_REQUEST = re.compile(
    r"\b(?:goodbye|bye(?:\s+bye)?|hang\s*up|end\s+(?:the\s+)?call|disconnect|"
    r"that's\s+all|that\s+is\s+all|i(?:'m| am)\s+done|we(?:'re| are)\s+done)\b"
    r"|अलविदा|बस\s+इतना\s+ही|कॉल\s+काट|बंद\s+कर(?:ो|ें)|"
    r"వీడ్కోలు|ఇంతే|కాల్\s+కట్|ముగించు|"
    r"விடைபெறுகிறேன்|அவ்வளவுதான்|அழைப்பை\s+முடி|"
    r"বিদায়|এইটুকুই|কল\s+কেটে|"
    r"বিদায়|बस\s+झालं|इथेच\s+थांबू|"
    r"વિદાય|બસ\s+આટલું|કૉલ\s+બંધ|"
    r"ವಿದಾಯ|ಇಷ್ಟೇ|ಕರೆ\s+ಮುಗಿಸು|"
    r"വിട|ഇത്രയും\s+മതി|കോൾ\s+അവസാനിപ്പി|"
    r"ଭଲ\s+ଥାଅ|ଏତିକି|କଲ୍\s+କାଟ|"
    r"বিদায়|এতটুকুই|কথা\s+শেষ|"
    r"الوداع|بس\s+هذا|أنه(?:ي|ِ)\s+المكالمة|"
    r"خداحافظ|همین\s+کافیه|تماس\s+رو\s+قطع|"
    r"خدا حافظ|بس\s+این\s+قدر|کال\s+ختم|"
    r"خدای\s+په\s+امان|همدومره|"
    r"دا\s+ختم|تماس\s+قطع|"
    r"خداینگهدار|بس\s+ايترو|فون\s+بند",
    re.IGNORECASE,
)


def _message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def caller_explicitly_ends(messages: list[dict] | None) -> bool:
    """Only treat a clear caller farewell as permission to end a live call."""
    if not isinstance(messages, list):
        return False
    latest_user = next(
        (message for message in reversed(messages)
         if isinstance(message, dict) and message.get("role") == "user"),
        None,
    )
    return bool(
        latest_user
        and _EXPLICIT_END_REQUEST.search(_message_text(latest_user))
    )


def _suppress_assist_route_instructions(messages: list[dict]) -> None:
    """Remove the prompt-side handoff instruction when its tool is suppressed."""
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "system":
            continue
        content = _message_text(message)
        if "Workflow step routing:" not in content or "assist_caller" not in content:
            continue
        blocks = content.split("\n\n")
        kept_blocks = []
        for block in blocks:
            if not block.startswith("Workflow step routing:"):
                kept_blocks.append(block)
                continue
            lines = block.splitlines()
            routes = [line for line in lines if line.lstrip().startswith("- ")]
            remaining = [line for line in routes if "assist_caller:" not in line]
            if remaining:
                kept_blocks.append("\n".join(
                    [line for line in lines if not line.lstrip().startswith("- ")]
                    + remaining
                ))
        message["content"] = "\n\n".join(kept_blocks)


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
    from api.services.workflow.tools.booking import caller_confirmed_booking

    caller_text = _message_text(last)
    if not caller_confirmed_booking(messages) or _NEGATION.search(caller_text):
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
    def create_client(
        self,
        api_key=None,
        base_url=None,
        organization=None,
        project=None,
        default_headers=None,
        **kwargs,
    ):
        """Bound provider stalls so a voice turn cannot wait for SDK retries for minutes."""
        return AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            organization=organization,
            project=project,
            default_headers=default_headers,
            http_client=DefaultAsyncHttpxClient(timeout=45.0),
            max_retries=0,
        )

    async def _process_context(self, context):
        from uuid import uuid4

        from api.services.workflow.confirmed_booking import confirmed_booking_arguments
        from pipecat.services.llm_service import FunctionCallFromLLM

        messages = context.get_messages()
        tools = getattr(context.tools, "standard_tools", [])
        user_messages = [
            message for message in messages
            if isinstance(message, dict) and message.get("role") == "user"
        ]
        if (
            len(user_messages) == 1
            and any(getattr(tool, "name", None) == "book_appointment" for tool in tools)
            and _BOOKING_REQUEST.search(_message_text(user_messages[-1]))
            and not _CALLER_NAME.search(_message_text(user_messages[-1]))
        ):
            # Small CPU models can take many seconds to ask this obvious
            # question, and often repeat date/time details already supplied.
            # Send it through the normal transcript and TTS path without an
            # extra inference request.
            caller_text = _message_text(user_messages[-1])
            if re.search(r"[\u0900-\u097f]", caller_text):
                reply = "ज़रूर। अपॉइंटमेंट किस नाम से बुक करूँ?"
            elif re.search(r"\b(?:mujhe|mera|naam|karna|chahiye|haan)\b", caller_text, re.IGNORECASE):
                reply = "Bilkul. Appointment kis naam se book karun?"
            else:
                reply = "Sure. What name should I use for the appointment?"
            await self.start_ttfb_metrics()
            await self.push_frame(LLMFullResponseStartFrame())
            await self._push_llm_text(reply)
            await self.push_frame(LLMFullResponseEndFrame())
            return
        if (
            messages and isinstance(messages[-1], dict)
            and messages[-1].get("role") == "user"
            and any(getattr(tool, "name", None) == "book_appointment" for tool in tools)
        ):
            arguments = confirmed_booking_arguments(_message_text(messages[-1]))
            if arguments:
                # Use the registered native handler so org ownership, caller
                # consent, persistence and normal tool-result frames are shared
                # by web and telephone calls. No model request is necessary.
                await self.run_function_calls([FunctionCallFromLLM(
                    context=context, function_name="book_appointment",
                    tool_call_id=f"confirmed_booking_{uuid4().hex}", arguments=arguments,
                )])
                return
        await super()._process_context(context)

    def build_chat_completion_params(self, params_from_context):
        params = super().build_chat_completion_params(params_from_context)
        from api.services.workflow.tools.booking import caller_confirmed_booking

        tools = params.get("tools")
        messages = params.get("messages")
        suppress_assist_handoff = False
        if isinstance(tools, list) and isinstance(messages, list):
            # The Start node has already spoken its greeting. A basic caller
            # check such as "hello, are you listening?" needs an answer from
            # that node, not an extra model call that only hands control to the
            # next node. Keep operational tools (booking, etc.) available.
            opening = next((
                message for message in messages
                if isinstance(message, dict) and message.get("role") == "assistant"
            ), None)
            if (
                opening is not None
                and _OPENING_GREETING.search(_message_text(opening))
                and any(
                    isinstance(tool, dict)
                    and tool.get("function", {}).get("name") == "assist_caller"
                    for tool in tools
                )
            ):
                # The generated Start node already has this assistant's full
                # prompt and operational tools. Treat the greeting as the
                # conversation start, so a redundant assist_caller edge cannot
                # burn another inference turn for the same conversation.
                suppress_assist_handoff = True
            if suppress_assist_handoff:
                _suppress_assist_route_instructions(messages)
                persona_note = ""
                if re.search(r"\basha\b|आशा", _message_text(opening), re.IGNORECASE):
                    persona_note = (
                        " For Asha, use feminine Hindi forms (for example, मैं सुन रही "
                        "हूँ and कर सकती हूँ), not masculine forms."
                    )
                direct_reply_text = (
                    "This current node already has the complete assistant prompt "
                    "and tools. Continue the conversation here; do not call "
                    "assist_caller or transfer to a duplicate assistant node."
                    f"{persona_note} In a booking task, "
                    "review all caller turns, do not ask again for details already "
                    "given, and ask one concise question for the next missing "
                    "booking detail. Never invent or claim a booking."
                )
                if not any(
                    isinstance(message, dict)
                    and message.get("role") == "system"
                    and direct_reply_text in _message_text(message)
                    for message in messages
                ):
                    direct_reply_note = {
                        "role": "system",
                        "content": direct_reply_text,
                    }
                else:
                    direct_reply_note = None
            else:
                direct_reply_note = None
            if direct_reply_note:
                first_user_index = next(
                    index for index, message in enumerate(messages)
                    if isinstance(message, dict) and message.get("role") == "user"
                )
                messages.insert(first_user_index, direct_reply_note)

        tools = params.get("tools")
        messages = params.get("messages")
        if (
            isinstance(tools, list) and isinstance(messages, list)
            and any(tool.get("function", {}).get("name") == "book_appointment"
                    for tool in tools if isinstance(tool, dict))
            and not caller_confirmed_booking(messages)
        ):
            # Match the native handler's consent requirement. This also keeps
            # small CPU models from spending a turn emitting an invalid booking
            # while the assistant is still gathering the caller's details.
            remaining = [tool for tool in tools
                         if tool.get("function", {}).get("name") != "book_appointment"]
            if remaining:
                params["tools"] = remaining
            else:
                params.pop("tools", None)
            selected = params.get("tool_choice")
            if not remaining or (isinstance(selected, dict)
                                 and selected.get("function", {}).get("name") == "book_appointment"):
                params.pop("tool_choice", None)
        # Booking-tool filtering above may rebuild the list of remaining tools;
        # reapply transition guards last so a hidden handoff/end tool cannot be
        # accidentally restored as a side effect.
        tools = params.get("tools")
        messages = params.get("messages")
        if isinstance(tools, list):
            latest_user_text = next((
                _message_text(message) for message in reversed(messages or [])
                if isinstance(message, dict) and message.get("role") == "user"
            ), "")
            disallowed = set()
            if suppress_assist_handoff:
                disallowed.add("assist_caller")
            if not _EXPLICIT_END_REQUEST.search(latest_user_text):
                disallowed.update(_END_CALL_TOOLS)
            if disallowed:
                remaining = [
                    tool for tool in tools
                    if tool.get("function", {}).get("name") not in disallowed
                ]
                if remaining:
                    params["tools"] = remaining
                else:
                    params.pop("tools", None)
                    params.pop("tool_choice", None)
                selected = params.get("tool_choice")
                if (isinstance(selected, dict)
                        and selected.get("function", {}).get("name") in disallowed):
                    params.pop("tool_choice", None)
        choice = booking_tool_choice(params)
        messages = params.get("messages")
        if isinstance(messages, list):
            user_messages = [
                message for message in messages
                if isinstance(message, dict) and message.get("role") == "user"
            ]
            opening = next((
                message for message in messages
                if isinstance(message, dict) and message.get("role") == "assistant"
            ), None)
            # Small local models often copy a configured Start-node greeting
            # verbatim even when the prompt tells them not to greet again.
            # The greeting has already played, so omit its text on the first
            # caller turn and retain that fact as an explicit system message.
            if (
                len(user_messages) == 1
                and opening is not None
                and _OPENING_GREETING.search(_message_text(opening))
            ):
                messages = [message for message in messages if message is not opening]
                opening_note = {
                    "role": "system",
                    "content": (
                        "The configured opening greeting has already been spoken. "
                        "Answer the caller's latest message directly; do not greet, "
                        "introduce yourself, or repeat the opening words."
                    ),
                }
                insert_at = (
                    1 if messages and isinstance(messages[0], dict)
                    and messages[0].get("role") == "system" else 0
                )
                messages.insert(insert_at, opening_note)
                params["messages"] = messages
        if isinstance(messages, list) and messages:
            latest_user = next((message for message in reversed(messages) if isinstance(message, dict) and message.get("role") == "user"), None)
            if latest_user and _CONFIRMATION.search(_message_text(latest_user)):
                tools = params.get("tools")
                logger.info(
                    "Confirmed booking selection: last_role={}, tool_names={}, forced={}",
                    messages[-1].get("role") if isinstance(messages[-1], dict) else type(messages[-1]).__name__,
                    [tool.get("function", {}).get("name") for tool in tools if isinstance(tool, dict)] if isinstance(tools, list) else type(tools).__name__,
                    bool(choice),
                )
        if choice:
            params["tool_choice"] = choice
            # Some local OpenAI-compatible engines treat a named tool choice
            # as a hint. Keep routing tools from competing with this confirmed
            # calendar action, and make the instruction explicit in context.
            params["tools"] = [
                tool for tool in params["tools"]
                if tool.get("function", {}).get("name") == "book_appointment"
            ]
            params["messages"] = [*params["messages"], {
                "role": "system",
                "content": (
                    "The caller has explicitly confirmed an appointment. Continue "
                    "this conversation; do not greet again. Call book_appointment "
                    "using only the caller's stated name, phone, date, time and "
                    "timezone. Do not invent missing details. If any required "
                    "detail is missing, ask for that detail instead."
                ),
            }]
        return params


class BookingOpenAILLMService(_BookingToolChoiceMixin, OpenAILLMService):
    """OpenAI-compatible provider with confirmed-booking action enforcement."""


class BookingKodewavesLLMService(_BookingToolChoiceMixin, KodewavesLLMService):
    """Sovereign Ollama provider with confirmed-booking action enforcement."""
