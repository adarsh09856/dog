"""Provider-neutral caller context shared by every cascade agent LLM."""

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


_BASE_POLICY = (
    "Keep the conversation state across turns. Use the latest caller intent and "
    "all usable caller details already provided. Ask only for the next missing "
    "or unclear detail, one concise question at a time. Do not restart the flow, "
    "repeat answered questions or greetings, invent details, or claim an action "
    "succeeded without a successful tool result. Follow the active speech-language "
    "settings and the caller's latest clear language choice."
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

    def __init__(self, llm_service, policy_state: CallerContextPolicyState):
        super().__init__()
        self._llm_service = llm_service
        self._policy_state = policy_state
        self._phone_followup = None

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
        state = getattr(self._llm_service, "_contact_conversation_state", None)
        if not isinstance(state, dict):
            state = {}
            self._llm_service._contact_conversation_state = state
        remember_recent_caller_statements(messages, state)
        remember_explicit_caller_name(messages, state)

        # Resolve phone capture and confirmation before calling any provider.
        # This is the same shared parser used by the local-provider mixin, now
        # available to native and custom cascade LLM services too.
        from api.services.workflow.contact_context import caller_phone_fragment_reply

        tools = getattr(getattr(context, "tools", None), "standard_tools", [])
        booking_available = any(
            getattr(tool, "name", None) == "book_appointment" for tool in tools
        )
        phone_reply = caller_phone_fragment_reply(
            messages, state, booking_available=booking_available
        )
        self._phone_followup = phone_reply

        from api.services.pipecat.caller_language_context import (
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
        if isinstance(latest_text, str):
            source = getattr(self._llm_service, "_caller_language_source", None)
            supported = reply_language_switch_capabilities(
                getattr(self._llm_service, "_caller_language_supported_codes", None),
                source,
            )
            requested = standalone_language_request(latest_text, supported)
            select_language = getattr(source, "select_caller_language", None)
            if requested:
                selected = True
                if callable(select_language):
                    try:
                        selected = await select_language(requested)
                    except Exception:
                        selected = False
                if selected is not False:
                    state["reply_language"] = requested
            sync_contact_reply_language(state, source)

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

        message = {"role": "system", "content": policy}
        first_user = next(
            (index for index, item in enumerate(messages)
             if isinstance(item, dict) and item.get("role") == "user"),
            len(messages),
        )
        messages.insert(first_user, message)
        self._policy_state.context = context
        self._policy_state.message = message

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            # A previous provider failure may have skipped its normal end frame.
            self._policy_state.remove()
            self._phone_followup = None
            await self._prepare_context(frame)

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
