"""Require the calendar action when a caller explicitly confirms a booking."""

import re
import time
from loguru import logger
from openai import APIError, AsyncOpenAI, DefaultAsyncHttpxClient

from pipecat.services.kodewaves.llm import KodewavesLLMService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.utils.run_context import get_current_run_id

_CONFIRMATION = re.compile(r"\b(confirm(?:ed)?|save|proceed|book it)\b|पुष्टि|पक्क[ाी]|सेव", re.IGNORECASE)
_BOOKING = re.compile(r"\b(appointment|booking|consultation|reservation)\b|अपॉइंटमेंट|बुकिंग|नियुक्ति", re.IGNORECASE)
_NEGATION = re.compile(r"\b(don't|do not|not now|cancel|stop|never|no,?\s)\b|मत\s|नहीं", re.IGNORECASE)
_OPENING_GREETING = re.compile(
    r"^\s*(?:नमस्ते|नमस्कार|सुप्रभात|शुभ संध्या|namaste|hello|hi|good morning|good afternoon|good evening)",
    re.IGNORECASE,
)
_OPENING_WORDS = (
    "नमस्ते", "नमस्कार", "सुप्रभात", "शुभ संध्या", "namaste", "hello",
    "hi", "good morning", "good afternoon", "good evening",
)
_GREETING_SEPARATORS = " \t\r\n!,.:;?।॥،؛"
from api.services.workflow.direct_caller_reply import END_CALL_TOOL_NAMES as _END_CALL_TOOLS
_LOCAL_CALLER_RESPONSE_GUARD = (
    "Answer in the caller's language. Use their known name and contact details; ask "
    "only for the next missing or corrected detail. Never repeat an earlier reply or "
    "invent service names. Never claim an action succeeded without tool success. "
    "For bookings, retain every caller-provided service, date, "
    "and time. Ask one short clarification only when needed; never guess a date, year, "
    "or time. After the date is clear, ask only for the time. Keep spoken replies "
    "concise: use one short sentence when possible, and include every detail needed "
    "to answer safely without repeating information the caller already gave."
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


_ROMAN_HINDI_WORDS = frozenset({
    "aap", "aapka", "aapki", "apna", "apni", "batao", "bataiye", "hai",
    "hain", "hume", "kal", "karna", "karni", "kya", "main", "mera",
    "meri", "mujhe", "nahi", "nahin", "tha", "thi",
})
_ENGLISH_WORDS = frozenset({
    "can", "could", "don't", "how", "i", "is", "my", "need", "please",
    "should", "the", "want", "we", "what", "when", "where", "why", "would",
    "you",
})


def _clearly_english_caller_text(text: str) -> bool:
    """Avoid imposing English on Indic script or Romanized Hindi turns."""
    if any(char.isalpha() and not char.isascii() for char in text):
        return False
    words = [word.casefold() for word in re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text)]
    return (
        len(words) >= 3
        and not any(word in _ROMAN_HINDI_WORDS for word in words)
        and any(word in _ENGLISH_WORDS for word in words)
    )


def _without_hidden_transition_guidance(content: str, hidden: set[str]) -> str:
    """Filter only generated routing paragraphs, never caller or role text."""
    paragraphs = []
    for paragraph in content.split("\n\n"):
        if paragraph.startswith("Workflow step routing:"):
            lines = paragraph.splitlines()
            routes = [line for line in lines[1:] if not any(
                line.startswith(f"- {name}:") for name in hidden
            )]
            if not routes:
                continue
            paragraph = "\n".join([lines[0], *routes])
        paragraphs.append(paragraph)
    return "\n\n".join(paragraphs)


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
    async def get_chat_completions(self, context):
        """Trace model first-output versus generation time without caller text."""
        started = time.perf_counter()
        stream = await super().get_chat_completions(context)
        headers_ms = (time.perf_counter() - started) * 1000

        async def traced_stream():
            first_event_ms = None
            first_output_ms = None
            chunks = 0
            prompt_tokens = None
            cached_prompt_tokens = None
            completion_tokens = None
            finish_reason = None
            complete = False
            messages = []
            try:
                messages = context.get_messages() or []
            except (AttributeError, TypeError):
                pass
            message_chars = sum(
                len(message.get("content", ""))
                for message in messages
                if isinstance(message, dict)
                and isinstance(message.get("content"), str)
            )
            system_prompt = getattr(
                getattr(self, "_settings", None), "system_instruction", None
            )
            system_chars = len(system_prompt) if isinstance(system_prompt, str) else 0
            tools = getattr(context, "tools", None)
            tool_count = len(getattr(tools, "standard_tools", []) or [])
            try:
                async for chunk in stream:
                    now = time.perf_counter()
                    chunks += 1
                    if first_event_ms is None:
                        first_event_ms = (now - started) * 1000
                    usage = getattr(chunk, "usage", None)
                    if usage is not None:
                        prompt_tokens = getattr(usage, "prompt_tokens", prompt_tokens)
                        prompt_details = getattr(usage, "prompt_tokens_details", None)
                        if isinstance(prompt_details, dict):
                            cached_prompt_tokens = prompt_details.get(
                                "cached_tokens", cached_prompt_tokens
                            )
                        elif prompt_details is not None:
                            cached_prompt_tokens = getattr(
                                prompt_details, "cached_tokens", cached_prompt_tokens
                            )
                        completion_tokens = getattr(
                            usage, "completion_tokens", completion_tokens
                        )
                    choices = getattr(chunk, "choices", None) or []
                    if choices:
                        choice = choices[0]
                        delta = getattr(choice, "delta", None)
                        content = getattr(delta, "content", None) if delta else None
                        tool_calls = getattr(delta, "tool_calls", None) if delta else None
                        if first_output_ms is None and (content or tool_calls):
                            first_output_ms = (now - started) * 1000
                        finish_reason = getattr(choice, "finish_reason", None) or finish_reason
                    yield chunk
                complete = True
            finally:
                trace_payload = {
                    "model": getattr(getattr(self, "_settings", None), "model", None),
                    "usage_context": getattr(self, "_usage_context", None)
                    or "conversation_or_shared_inference",
                    "headers_ms": round(headers_ms, 1),
                    "first_event_ms": round(first_event_ms, 1)
                    if first_event_ms is not None else None,
                    "first_output_ms": round(first_output_ms, 1)
                    if first_output_ms is not None else None,
                    "total_ms": round((time.perf_counter() - started) * 1000, 1),
                    "chunks": chunks,
                    "prompt_tokens": prompt_tokens,
                    "cached_prompt_tokens": cached_prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "history_messages": len(messages),
                    "history_chars": message_chars,
                    "system_chars": system_chars,
                    "tools": tool_count,
                    "finish_reason": finish_reason,
                    "complete": complete,
                }
                logger.info(
                    "llm_stream_trace run={} model={} usage_context={} headers_ms={} first_event_ms={} first_output_ms={} total_ms={} chunks={} prompt_tokens={} cached_prompt_tokens={} completion_tokens={} history_messages={} history_chars={} system_chars={} tools={} finish_reason={} complete={}",
                    get_current_run_id(),
                    getattr(getattr(self, "_settings", None), "model", None),
                    getattr(self, "_usage_context", None) or "conversation_or_shared_inference",
                    round(headers_ms, 1),
                    round(first_event_ms, 1) if first_event_ms is not None else None,
                    round(first_output_ms, 1) if first_output_ms is not None else None,
                    round((time.perf_counter() - started) * 1000, 1),
                    chunks,
                    prompt_tokens,
                    cached_prompt_tokens,
                    completion_tokens,
                    len(messages),
                    message_chars,
                    system_chars,
                    tool_count,
                    finish_reason,
                    complete,
                )
                trace_sink = getattr(self, "_llm_trace_sink", None)
                if callable(trace_sink):
                    try:
                        await trace_sink({
                            "type": "rtf-llm-stream-trace",
                            "payload": trace_payload,
                        })
                    except Exception as exc:
                        logger.debug(
                            "Could not persist numeric LLM stream diagnostics ({})",
                            type(exc).__name__,
                        )
                close = getattr(stream, "close", None)
                if callable(close):
                    await close()

        return traced_stream()

    async def _emit_direct_reply(self, text: str):
        # Fast replies bypass the model, so do not emit an LLM TTFB sample of
        # zero. That value is misleading in the live transcript; real model
        # requests still report their own TTFB through the normal service.
        await self._push_llm_text(text)

    def can_speculate_caller_turn(self, text: str) -> bool:
        """Keep confirmed-only contact/settings handling out of speculation."""
        from api.services.pipecat.caller_language_context import standalone_language_request
        from api.services.workflow.contact_context import (
            caller_name_followup_reply,
            caller_phone_fragment_reply,
        )
        from api.services.workflow.direct_caller_reply import direct_caller_reply

        state = dict(getattr(self, "_contact_conversation_state", {}))
        if standalone_language_request(text) or state.get("awaiting_phone"):
            return False
        if direct_caller_reply(text, has_lookup_tools=False):
            return False
        provider = getattr(self, "_contact_context_messages_provider", None)
        messages = list(provider()) if callable(provider) else []
        messages.append({"role": "user", "content": text})
        if caller_phone_fragment_reply(messages, state) is not None:
            return False
        return caller_name_followup_reply(messages, state) is None

    async def _run_or_defer_function_calls(self, function_calls, *, text_generated):
        # A tool-only completion is valid silence while its registered handler
        # runs. Distinguish it from a successful but empty model response.
        if function_calls:
            self._completion_has_tool_calls = True
        return await super()._run_or_defer_function_calls(
            function_calls, text_generated=text_generated,
        )

    async def _push_llm_text(self, text: str):
        if getattr(self, "_strip_repeated_greeting", False) and not getattr(
            self, "_opening_text_decided", False
        ):
            self._opening_text_buffer = getattr(self, "_opening_text_buffer", "") + text
            buffered = self._opening_text_buffer
            candidate = buffered.lstrip().casefold()
            if any(word.startswith(candidate) for word in _OPENING_WORDS):
                return  # Wait only while a streamed token could be a greeting.
            for word in _OPENING_WORDS:
                if candidate.startswith(word) and (
                    len(candidate) == len(word) or candidate[len(word)] in _GREETING_SEPARATORS
                ):
                    # The greeting has already played. Keep the rest of this
                    # chunk intact so transcript, TTS and recording agree.
                    text = buffered.lstrip()[len(word):].lstrip(_GREETING_SEPARATORS)
                    self._opening_text_buffer = ""
                    self._opening_text_decided = bool(text)
                    self._greeting_suppressed = True
                    if not text:
                        return
                    break
            else:
                text = buffered
                self._opening_text_buffer = ""
                self._opening_text_decided = True
        if text and text.strip():
            self._completion_has_text = True
        await super()._push_llm_text(text)

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

        # Speculative responses are held and may be discarded if speech resumes.
        # Keep deterministic shortcuts out of this pass because some of them
        # update conversation state before the speculation gate can confirm it.
        if getattr(getattr(self, "_speculation_gate", None), "is_speculating", False):
            return await super()._process_context(context)

        messages = context.get_messages()
        self._strip_repeated_greeting = False
        self._opening_text_decided = False
        self._opening_text_buffer = ""
        self._greeting_suppressed = False
        tools = getattr(context.tools, "standard_tools", [])
        from api.services.workflow.contact_context import (
            booking_contact_question,
            caller_name_followup_reply,
            caller_phone_fragment_reply,
            remember_recent_caller_statements,
            remember_explicit_caller_name,
        )
        from api.services.workflow.direct_caller_reply import direct_caller_reply

        contact_state = getattr(self, "_contact_conversation_state", None)
        if not isinstance(contact_state, dict):
            contact_state = {}
            self._contact_conversation_state = contact_state
        remember_recent_caller_statements(messages, contact_state)

        latest_user_text = (
            _message_text(messages[-1])
            if messages and isinstance(messages[-1], dict)
            and messages[-1].get("role") == "user" else ""
        )
        from api.services.pipecat.caller_language_context import (
            CallerLanguageContext,
            standalone_language_request,
            sync_contact_reply_language,
        )

        requested_language = standalone_language_request(latest_user_text)
        if requested_language:
            if not hasattr(self, "_caller_language_context"):
                self._caller_language_context = CallerLanguageContext()
            source = getattr(self, "_caller_language_source", None)
            select_recognition = getattr(source, "select_caller_language", None)
            if callable(select_recognition):
                try:
                    await select_recognition(requested_language)
                except Exception:
                    # The reply choice remains valid even when recognition
                    # inventory is temporarily unavailable. Keep errors free
                    # of endpoint credentials and caller text.
                    logger.warning("Caller recognition-language switch unavailable")
            self._caller_language_context.choose_language(
                requested_language, source, text=latest_user_text
            )
            self._caller_language_context.apply(messages, source)
            state = getattr(self, "_contact_conversation_state", None)
            if not isinstance(state, dict):
                state = {}
                self._contact_conversation_state = state
            state["reply_language"] = requested_language
            await self._emit_direct_reply(
                "Yes, we can continue in English."
                if requested_language == "English"
                else "ज़रूर, हम हिंदी में बात कर सकते हैं।"
            )
            return

        # Deterministic contact replies run before the normal LLM-parameter
        # hook. Refresh the call-scoped language route here so phone/date
        # follow-ups do not keep an old explicit language after auto routing
        # has already switched the caller back to Hindi or English.
        source = getattr(self, "_caller_language_source", None)
        if source is not None:
            if not hasattr(self, "_caller_language_context"):
                self._caller_language_context = CallerLanguageContext()
            self._caller_language_context.apply(messages, source)
            sync_contact_reply_language(contact_state, source)

        direct_reply = direct_caller_reply(
            latest_user_text,
            # Ending a call cannot retrieve an order. Other tools remain
            # eligible for workflow routing and live lookups.
            has_lookup_tools=any(
                getattr(tool, "name", None) not in _END_CALL_TOOLS
                for tool in tools
            ),
        )
        if direct_reply:
            state = getattr(self, "_contact_conversation_state", None)
            if isinstance(state, dict):
                state.pop("pending_phone", None)
            await self._emit_direct_reply(direct_reply)
            return

        contact_state = getattr(self, "_contact_conversation_state", None)
        if not isinstance(contact_state, dict):
            contact_state = {}
            self._contact_conversation_state = contact_state
        known_name_reply = remember_explicit_caller_name(messages, contact_state)
        if known_name_reply:
            await self._emit_direct_reply(known_name_reply)
            return
        phone_fragment_reply = caller_phone_fragment_reply(messages, contact_state)
        if phone_fragment_reply:
            await self._emit_direct_reply(phone_fragment_reply)
            return
        booking_tool_available = any(
            getattr(tool, "name", None) == "book_appointment" for tool in tools
        )
        known_phone = (getattr(self, "_known_contact", {}) or {}).get("customer_phone")
        name_followup_reply = caller_name_followup_reply(
            messages, contact_state,
            booking_available=booking_tool_available,
            known_phone=known_phone,
        )
        if name_followup_reply:
            await self._emit_direct_reply(name_followup_reply)
            return

        known = getattr(self, "_known_contact", {})
        contact_state = getattr(self, "_contact_conversation_state", None)
        if contact_state:
            if contact_state.get("caller_name"):
                known = {**known, "customer_name": contact_state["caller_name"]}
            if contact_state.get("caller_phone"):
                known = {**known, "customer_phone": contact_state["caller_phone"]}
        has_booking_tool = any(getattr(tool, "name", None) == "book_appointment" for tool in tools)
        if (
            messages and isinstance(messages[-1], dict)
            and messages[-1].get("role") == "user"
            and any(getattr(tool, "name", None) == "book_appointment" for tool in tools)
        ):
            from api.services.workflow.contact_context import confirmed_staged_booking_arguments
            from api.services.workflow.confirmed_booking import room_booking_active

            arguments = None if room_booking_active(messages) else confirmed_booking_arguments(_message_text(messages[-1]))
            if not arguments:
                arguments = confirmed_staged_booking_arguments(
                    messages, contact_state if isinstance(contact_state, dict) else {}, known
                )
            if arguments:
                # Use the registered native handler so org ownership, caller
                # consent, persistence and normal tool-result frames are shared
                # by web and telephone calls. No model request is necessary.
                await self.run_function_calls([FunctionCallFromLLM(
                    context=context, function_name="book_appointment",
                    tool_call_id=f"confirmed_booking_{uuid4().hex}", arguments=arguments,
                )])
                return
        fast_booking_question = None
        if has_booking_tool:
            fast_booking_question = booking_contact_question(
                messages, known, contact_state if contact_state is not None else {}
            )
        if fast_booking_question:
            # Only ask for intake details after the strict complete-confirmation
            # parser has had a chance to route a fully specified caller-approved
            # booking to the registered tool. Incomplete requests still take
            # this short path and avoid an unnecessary model round trip.
            await self._emit_direct_reply(fast_booking_question)
            return
        self._completion_has_text = False
        self._completion_has_tool_calls = False
        try:
            await super()._process_context(context)
            if self._opening_text_buffer:
                # A completion ending mid-word should not disappear.
                remainder, self._opening_text_buffer = self._opening_text_buffer, ""
                if remainder.strip().casefold() in _OPENING_WORDS:
                    self._greeting_suppressed = True
                else:
                    await super()._push_llm_text(remainder)
                    self._completion_has_text = bool(remainder.strip())
            if not self._completion_has_text and not self._completion_has_tool_calls:
                logger.warning("LLM completion returned no spoken text or executable tools")
                await self._push_llm_text(self._completion_recovery_text(messages))
        except (APIError, TimeoutError):
            # Keep the original error observable upstream, but give a caller
            # whose answer never started a normal transcript/TTS recovery.
            # Never append this to a partial answer or retry an external action.
            if not self._completion_has_text and not self._completion_has_tool_calls:
                await self._push_llm_text(self._completion_recovery_text(messages))
            raise

    def _completion_recovery_text(self, messages):
        from api.services.configuration.language_normalizer import normalize_language_code
        from api.services.pipecat.caller_language_context import _trusted_detected_language

        source = getattr(self, "_caller_language_source", None)
        settings = getattr(source, "_settings", None)
        # A recovery is spoken through the same TTS route as a normal reply.
        # Honor an explicit caller choice and the confidence-filtered route;
        # a weak raw detector label must not choose a different apology voice.
        preference = getattr(source, "reply_language_override", None)
        if not preference:
            preference = getattr(
                getattr(self, "_caller_language_context", None),
                "_explicit_preference", None,
            )
        language = preference or _trusted_detected_language(source) or getattr(settings, "language", None)
        language = getattr(language, "value", language)
        language = normalize_language_code(language)
        recovery = {
            "hi": "माफ़ कीजिए, जवाब देने में समस्या हुई। कृपया फिर से कोशिश करें।",
            "kn": "ಕ್ಷಮಿಸಿ, ಉತ್ತರ ನೀಡಲು ಸಮಸ್ಯೆಯಾಗಿದೆ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
            "ta": "மன்னிக்கவும், பதிலளிப்பதில் சிக்கல் ஏற்பட்டது. மீண்டும் முயற்சிக்கவும்.",
            "te": "క్షమించండి, సమాధానం ఇవ్వడంలో సమస్య వచ్చింది. దయచేసి మళ్లీ ప్రయత్నించండి.",
            "ml": "ക്ഷമിക്കണം, മറുപടി നൽകുന്നതിൽ പ്രശ്നമുണ്ടായി. ദയവായി വീണ്ടും ശ്രമിക്കുക.",
            "mr": "क्षमस्व, उत्तर देताना समस्या आली. कृपया पुन्हा प्रयत्न करा.",
            "en": "Sorry, I had trouble responding. Please try again.",
        }
        if language in recovery:
            return recovery[language]
        # Do not infer one of the several Devanagari languages from its script.
        # English fallback is available in the unified local speech engine.
        return recovery["en"]

    def build_chat_completion_params(self, params_from_context):
        params = super().build_chat_completion_params(params_from_context)
        initial_tool_names = {
            tool.get("function", {}).get("name")
            for tool in params.get("tools", []) or [] if isinstance(tool, dict)
        }
        # Routing and greeting guards below rewrite messages for this request.
        # The adapter can share message dictionaries with the conversation;
        # never remove routes or insert runtime guidance into that history.
        if isinstance(params.get("messages"), list):
            params["messages"] = [
                dict(message) if isinstance(message, dict) else message
                for message in params["messages"]
            ]
        model = str(getattr(self._settings, "model", "") or "").casefold()
        messages = params.get("messages")
        if model.startswith("qwen3:") and isinstance(messages, list):
            # Qwen3 supports a prompt-level switch. Qwen3.5 does not: control
            # its reasoning through the serving API without changing prompts.
            found_system_prompt = False
            for index in range(len(messages) - 1, -1, -1):
                message = messages[index]
                if not isinstance(message, dict) or message.get("role") != "system":
                    continue
                content = message.get("content")
                if isinstance(content, str):
                    found_system_prompt = True
                    if "/no_think" not in content:
                        messages = list(messages)
                        messages[index] = {
                            **message,
                            "content": f"{content.rstrip()}\n/no_think",
                        }
                        params["messages"] = messages
                    break
            if not found_system_prompt:
                first_user = next(
                    (index for index, message in enumerate(messages)
                     if isinstance(message, dict) and message.get("role") == "user"),
                    len(messages),
                )
                messages = list(messages)
                messages.insert(first_user, {"role": "system", "content": "/no_think"})
                params["messages"] = messages
        if (
            getattr(self, "_kodewaves_local_ollama", False)
            and model.startswith(("qwen3:", "qwen3.5:"))
            and isinstance(messages, list)
        ):
            # Ollama's OpenAI endpoint reads reasoning_effort and max_tokens.
            # Native /api/chat fields (think, options.num_thread/num_ctx/
            # num_predict) are silently ignored here. Thread/context tuning
            # must be persisted in the selected Ollama model's parameters so
            # native warm-up and OpenAI conversation requests use one runner.
            params["reasoning_effort"] = "none"
            extra_body = params.get("extra_body")
            params["extra_body"] = {
                **(extra_body if isinstance(extra_body, dict) else {}),
                # Prevent multi-minute model reloads on the first caller turn.
                # The OpenAI-compatible endpoint parses this as a Go duration;
                # a bare "-1" is rejected there (native /api/chat accepts -1).
                "keep_alive": "8760h",
            }
            # Ollama's OpenAI-compatible streaming API sends input/output usage
            # in a final chunk when requested. The trace wrapper records these
            # counts without logging caller text, letting production distinguish
            # slow prompt prefill from slow token generation.
            params["stream_options"] = {"include_usage": True}

        from api.services.workflow.tools.booking import caller_confirmed_booking

        # Transition names are user-defined. An assist_caller edge can lead
        # to a different role or toolset; only the workflow engine can decide
        # which destination to enter. Preserve its schema and routing prompt.
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
            # The greeting has already played, so omit it on every caller
            # turn. Restoring it on later turns encourages repeated greetings
            # and invalidates the local model's reusable prompt prefix.
            if (
                user_messages
                and opening is not None
                and _OPENING_GREETING.search(_message_text(opening))
            ):
                self._strip_repeated_greeting = model.startswith(("qwen2.5:", "qwen3:", "qwen3.5:"))
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
        if (
            getattr(self, "_kodewaves_local_ollama", False)
            and model.startswith(("qwen3:", "qwen3.5:"))
            and isinstance(messages, list)
            and any(
                isinstance(message, dict) and message.get("role") == "user"
                for message in messages
            )
        ):
            # Keep this guidance in a fixed system-prefix position. Inserting it
            # before the newest user message on every turn breaks Ollama's shared
            # prompt prefix and forces the CPU model to re-evaluate conversation history.
            if not any(
                isinstance(message, dict)
                and message.get("role") == "system"
                and message.get("content") == _LOCAL_CALLER_RESPONSE_GUARD
                for message in messages
            ):
                system_index = next((
                    index for index, message in enumerate(messages)
                    if isinstance(message, dict) and message.get("role") == "system"
                ), None)
                messages.insert(
                    system_index + 1 if system_index is not None else 0,
                    {"role": "system", "content": _LOCAL_CALLER_RESPONSE_GUARD},
                )
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
        # An empty conversation is the opening announcement, not a caller
        # request. Do not spend that turn routing away before anyone speaks.
        # Keep tool-result and assistant history eligible for normal routing.
        messages = params.get("messages")
        if isinstance(messages, list) and not any(
            isinstance(message, dict)
            and message.get("role") in {"user", "assistant", "tool"}
            for message in messages
        ):
            params.pop("tools", None)
            params.pop("tool_choice", None)
        available_tool_names = {
            tool.get("function", {}).get("name")
            for tool in params.get("tools", []) or [] if isinstance(tool, dict)
        }
        hidden = initial_tool_names - available_tool_names
        if hidden and isinstance(params.get("messages"), list):
            params["messages"] = [
                {**message, "content": _without_hidden_transition_guidance(message["content"], hidden)}
                if isinstance(message, dict) and message.get("role") == "system"
                and isinstance(message.get("content"), str) else message
                for message in params["messages"]
            ]
        messages = params.get("messages")
        if isinstance(messages, list) and getattr(self, "_kodewaves_local_ollama", False):
            from api.services.pipecat.runtime_clock_context import CallerClockContext

            if not hasattr(self, "_caller_clock_context"):
                contact_state = getattr(self, "_contact_conversation_state", None)
                state = contact_state.setdefault("_runtime_clock_context", {}) if isinstance(contact_state, dict) else None
                self._caller_clock_context = CallerClockContext(state)
            params["messages"] = self._caller_clock_context.apply(messages)
        # Preserve each recognized utterance's request-only language hint on
        # later turns. Removing old hints changes the prompt prefix and forces
        # CPU inference to reprocess conversation history unnecessarily.
        messages = params.get("messages")
        if (
            model.startswith(("qwen2.5:", "qwen3:", "qwen3.5:"))
            and isinstance(messages, list)
        ):
            from api.services.pipecat.caller_language_context import CallerLanguageContext

            if not hasattr(self, "_caller_language_context"):
                self._caller_language_context = CallerLanguageContext()
            params["messages"] = self._caller_language_context.apply(
                messages, getattr(self, "_caller_language_source", None)
            )
        if getattr(self, "_kodewaves_local_ollama", False):
            from api.services.workflow.contact_context import caller_state_instruction

            messages = params.get("messages")
            reminder = caller_state_instruction(
                getattr(self, "_contact_conversation_state", None),
                messages if isinstance(messages, list) else None,
            )
            if isinstance(messages, list):
                from api.services.pipecat.caller_state_context import CallerStateContext

                contact_state = getattr(self, "_contact_conversation_state", None)
                if not isinstance(contact_state, dict):
                    contact_state = {}
                    self._contact_conversation_state = contact_state
                state = contact_state.setdefault("_caller_state_context", {})
                if not hasattr(self, "_caller_state_context"):
                    self._caller_state_context = CallerStateContext(state)
                params["messages"] = self._caller_state_context.apply(messages, reminder)
        messages = params.get("messages")
        if isinstance(messages, list) and not getattr(self, "_kodewaves_local_ollama", False):
            from api.services.pipecat.runtime_clock_context import add_current_clock

            params["messages"] = add_current_clock(messages)
        return params


class BookingOpenAILLMService(_BookingToolChoiceMixin, OpenAILLMService):
    """OpenAI-compatible provider with confirmed-booking action enforcement."""


class BookingKodewavesLLMService(_BookingToolChoiceMixin, KodewavesLLMService):
    """Sovereign Ollama provider with confirmed-booking action enforcement."""
