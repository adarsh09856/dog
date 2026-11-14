"""Provider-neutral caller context shared by every cascade agent LLM."""

from copy import deepcopy
import inspect
import re

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    LLMContextFrame,
    LLMFullResponseStartFrame,
    LLMFullResponseEndFrame,
    LLMTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


_BASE_POLICY = (
    "Keep the conversation state across turns. Use the latest caller intent and "
    "all usable caller details already provided. Ask only for the next missing "
    "or unclear detail, one concise question at a time. Do not restart the flow, "
    "repeat answered questions or greetings, invent details, or claim an action "
    "succeeded without a successful tool result. Follow the active speech-language "
    "settings and the caller's latest clear language choice. When the caller mixes "
    "languages, answer in the same natural mix, including Hinglish; preserve names, "
    "digits, dates, and times exactly, and do not translate unless asked."
)


class CallerContextPolicyState:
    def __init__(self):
        self.context = None
        self.message = None

    def remove(self):
        context, message = self.context, self.message
        self.context = None
        self.message = None
        if context is None or message is None:
            return
        messages = context.get_messages()
        index = next(
            (index for index, item in enumerate(messages) if item is message),
            None,
        )
        if index is not None:
            messages.pop(index)


class CallerContextPolicyProcessor(FrameProcessor):
    """Add temporary call-scoped caller facts before a provider generates text.

    The policy is removed before the LLM response reaches the shared assistant
    history, keeping provider-specific request formats and tools untouched.
    """

    def __init__(
        self,
        llm_service,
        policy_state: CallerContextPolicyState,
        *,
        handle_contact_fallbacks: bool = True,
    ):
        super().__init__()
        self._llm_service = llm_service
        self._policy_state = policy_state
        self._handle_contact_fallbacks = handle_contact_fallbacks
        self._phone_followup = None
        self._direct_reply = None

    async def _emit_direct_reply(self, text: str) -> bool:
        """Push deterministic follow-ups through the normal transcript/TTS path."""
        push_frame = getattr(self._llm_service, "push_frame", None)
        if not callable(push_frame):
            return False
        speculation_gate = getattr(self._llm_service, "_speculation_gate", None)
        begin_speculation = getattr(speculation_gate, "begin_speculation", None)
        if callable(begin_speculation):
            # This context is the confirmed, non-speculative turn that would
            # normally reset the provider gate before generation begins.
            begin_speculation(False)
        await push_frame(LLMFullResponseStartFrame())
        await push_frame(LLMTextFrame(text))
        await push_frame(LLMFullResponseEndFrame())
        return True

    async def _prepare_context(self, frame: LLMContextFrame):
        if frame.speculation:
            return

        from api.services.workflow.contact_context import (
            caller_state_instruction,
            remember_explicit_caller_name,
            remember_recent_caller_statements,
        )

        context = frame.context
        messages = context.get_messages()
        self._direct_reply = None
        state = getattr(self._llm_service, "_contact_conversation_state", None)
        if not isinstance(state, dict):
            state = {}
            self._llm_service._contact_conversation_state = state
        state_before = deepcopy(state)
        remember_recent_caller_statements(messages, state)
        name_memory_reply = (
            remember_explicit_caller_name(messages, state)
            if self._handle_contact_fallbacks else None
        )
        if name_memory_reply:
            self._direct_reply = name_memory_reply

        from api.services.pipecat.caller_language_context import (
            CallerLanguageContext,
            _requested_language,
            reply_language_switch_capabilities,
            standalone_language_request,
            sync_contact_reply_language,
        )

        latest_user = next(
            (item for item in reversed(messages)
             if isinstance(item, dict) and item.get("role") == "user"),
            None,
        )
        latest_text = latest_user.get("content", "") if latest_user else ""
        explicit_language_selected = False
        if isinstance(latest_text, str):
            source = getattr(self._llm_service, "_caller_language_source", None)
            supported = reply_language_switch_capabilities(
                getattr(self._llm_service, "_caller_language_supported_codes", None),
                source,
            )
            language_context = getattr(
                self._llm_service, "_caller_language_context", None
            )
            if not isinstance(language_context, CallerLanguageContext):
                language_context = CallerLanguageContext()
                self._llm_service._caller_language_context = language_context
            requested = _requested_language(latest_text, supported)
            standalone_request = standalone_language_request(latest_text, supported)
            select_language = getattr(source, "select_caller_language", None)
            if requested:
                selected = True
                if callable(select_language):
                    try:
                        selected = await select_language(requested)
                    except Exception:
                        selected = False
                if selected is not False:
                    language_context.choose_language(
                        requested, source, text=latest_text
                    )
                    # The context owns explicit preference lifetime and the
                    # recognizer's TTS override. Contact state below then uses
                    # that same validated route instead of the latest raw LID.
                    language_context.apply(
                        messages, source, supported_languages=supported
                    )
                    state["reply_language"] = requested
                    explicit_language_selected = True
                    if standalone_request:
                        self._direct_reply = (
                            "Yes, we can continue in English."
                            if requested == "English"
                            else "ज़रूर, हम हिंदी में बात कर सकते हैं।"
                        )
            else:
                # Keep the same call-scoped language state used by the booking
                # mixin. It preserves explicit choices across turns and clears
                # them only when a later, supported caller language resumes
                # automatic routing.
                language_context.apply(
                    messages, source, supported_languages=supported
                )
            phone_capture_turn = bool(
                state.get("awaiting_phone")
                or state.get("caller_phone_confirmation_pending")
            )
            if not explicit_language_selected and not phone_capture_turn:
                sync_contact_reply_language(state, source)

        # Resolve phone capture after language selection so a clear language
        # request cannot be consumed as an invalid phone answer.
        from api.services.workflow.contact_context import caller_phone_fragment_reply

        tools = getattr(getattr(context, "tools", None), "standard_tools", [])
        booking_available = any(
            getattr(tool, "name", None) == "book_appointment" for tool in tools
        )
        phone_reply = None
        if self._handle_contact_fallbacks and not self._direct_reply:
            from api.services.workflow.contact_context import caller_name_followup_reply

            known_phone = (getattr(self._llm_service, "_known_contact", {}) or {}).get(
                "customer_phone"
            )
            name_followup = caller_name_followup_reply(
                messages,
                state,
                booking_available=booking_available,
                known_phone=known_phone,
            )
            if name_followup:
                self._direct_reply = name_followup
        if self._handle_contact_fallbacks and not self._direct_reply:
            phone_reply = caller_phone_fragment_reply(
                messages, state, booking_available=booking_available
            )
        self._phone_followup = phone_reply
        if phone_reply:
            self._direct_reply = phone_reply

        detail = caller_state_instruction(state, visible_messages=messages)
        language = state.get("reply_language")
        language_policy = (
            f" The caller explicitly requested {language}; continue in {language} "
            "until they clearly request another supported language."
            if isinstance(language, str) and language.strip()
            else ""
        )
        policy = _BASE_POLICY + language_policy
        if detail:
            policy += " " + detail
        if self._phone_followup:
            policy += (
                " The caller's phone confirmation was just handled and the number is "
                "already stored for this call. Do not ask them to confirm or repeat it "
                "again. Continue by asking only the next missing detail: "
                + self._phone_followup
            )
        if (
            self._handle_contact_fallbacks
            and booking_available
            and not self._direct_reply
        ):
            # Run the same contact-and-booking state machine before every
            # cascade provider. If it resolves the next follow-up, emit that
            # exact reply and skip the provider so a smaller/custom model
            # cannot repeat a stale question or invent a time.
            from api.services.workflow.contact_context import booking_contact_question

            contact = getattr(self._llm_service, "_known_contact", {})
            if not isinstance(contact, dict):
                contact = {}
            else:
                contact = dict(contact)
            if state.get("caller_name"):
                contact["customer_name"] = state["caller_name"]
            if state.get("caller_phone"):
                contact["customer_phone"] = state["caller_phone"]
            recent = state.get("recent_caller_statements")
            visible_user = {
                " ".join(item["content"].split()).casefold()
                for item in messages
                if isinstance(item, dict)
                and item.get("role") == "user"
                and isinstance(item.get("content"), str)
            }
            hidden_statements = [
                statement for statement in recent[-8:]
                if isinstance(statement, str)
                and " ".join(statement.split()).casefold() not in visible_user
            ] if isinstance(recent, list) else []
            parser_messages = [
                *({"role": "user", "content": statement} for statement in hidden_statements),
                *messages,
            ]
            self._direct_reply = booking_contact_question(
                parser_messages, contact, state
            )

        await self._emit_turn_trace(
            latest_text=latest_text,
            state_before=state_before,
            state_after=state,
            context=context,
            direct_reply=bool(self._direct_reply),
        )

        message = {"role": "system", "content": policy}
        # The policy contains changing caller facts and language preferences.
        # Inserting it before the first user invalidates the cached conversation
        # on every update. Preserve earlier history and put the current facts
        # beside the latest turn, without persisting them into caller history.
        latest_user = next(
            (index for index in range(len(messages) - 1, -1, -1)
             if isinstance(messages[index], dict)
             and messages[index].get("role") == "user"),
            len(messages),
        )
        messages.insert(latest_user, message)
        self._policy_state.context = context
        self._policy_state.message = message

    async def _emit_turn_trace(
        self, *, latest_text, state_before, state_after, context, direct_reply
    ):
        """Persist joinable policy metadata without caller text or fact values."""
        sink = getattr(self._llm_service, "_turn_diagnostic_sink", None)
        if not callable(sink):
            sink = getattr(self._llm_service, "_llm_trace_sink", None)
        if not callable(sink):
            return

        from api.services.configuration.language_normalizer import normalize_language_code

        def safe_config(value):
            if not isinstance(value, str) or not value.strip():
                return None
            value = value.strip()[:80]
            return value if all(char.isalnum() or char in "_.:/+-" for char in value) else None

        def safe_language(value):
            if not value:
                return None
            code = normalize_language_code(str(value))
            return code if code == "caller" or code.isalpha() and len(code) <= 3 else None

        source = getattr(self._llm_service, "_caller_language_source", None)
        runtime = getattr(self._llm_service, "_agent_runtime_configuration", {})
        runtime = runtime if isinstance(runtime, dict) else {}
        tools = getattr(getattr(context, "tools", None), "standard_tools", []) or []
        tool_names = sorted({
            name for tool in tools
            if isinstance((name := getattr(tool, "name", None)), str)
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}", name)
        })[:40]
        changed_keys = sorted(
            key for key in set(state_before) | set(state_after)
            if state_before.get(key) != state_after.get(key)
            and isinstance(key, str)
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", key)
        )[:40]
        detected = getattr(source, "latest_detected_language", None)
        chosen = getattr(source, "latest_tts_language", None)
        language = (state_after or {}).get("reply_language")
        event = {
            "type": "rtf-caller-context-trace",
            "payload": {
                "run_id": getattr(self._llm_service, "_workflow_run_id", None),
                "agent_visit_id": safe_config(
                    getattr(self._llm_service, "_agent_visit_id", None)
                ),
                "llm_provider": safe_config(runtime.get("llm_provider")),
                "llm_model": safe_config(runtime.get("llm_model") or getattr(
                    getattr(self._llm_service, "_settings", None), "model", None
                )),
                "stt_final_chars": len(latest_text.strip()) if isinstance(latest_text, str) else 0,
                "detected_language_code": safe_language(detected),
                "chosen_tts_language_code": safe_language(chosen),
                "reply_language_code": safe_language(language),
                "state_changed_keys": changed_keys,
                "available_tool_names": tool_names,
                "available_tool_count": len(tools),
                "policy_route": "fast_reply" if direct_reply else "llm_provider",
            },
        }
        try:
            result = sink(event)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            # Diagnostics must never delay or fail a caller's response.
            from loguru import logger

            logger.debug("Could not persist caller-context trace ({})", type(exc).__name__)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            # A previous provider failure may have skipped its normal end frame.
            self._policy_state.remove()
            self._phone_followup = None
            await self._prepare_context(frame)
            if self._direct_reply and await self._emit_direct_reply(self._direct_reply):
                self._policy_state.remove()
                self._direct_reply = None
                self._phone_followup = None
                return

        await self.push_frame(frame, direction)

    async def cleanup(self):
        await super().cleanup()


class CallerContextPolicyCleanupProcessor(FrameProcessor):
    """Remove the temporary policy after the provider has finished generation."""

    def __init__(self, policy_state: CallerContextPolicyState):
        super().__init__()
        self._policy_state = policy_state

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, (LLMFullResponseEndFrame, ErrorFrame, CancelFrame, EndFrame)):
            self._policy_state.remove()
        await self.push_frame(frame, direction)

    async def cleanup(self):
        self._policy_state.remove()
        await super().cleanup()
