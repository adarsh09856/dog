import asyncio

from pipecat.frames.frames import (
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection

from api.services.pipecat.caller_context_policy import (
    CallerContextPolicyProcessor,
    CallerContextPolicyState,
)


class _Tools:
    standard_tools = [type("Tool", (), {"name": "book_appointment"})()]


class _Context:
    def __init__(self, messages):
        self._messages = messages
        self.tools = _Tools()

    def get_messages(self):
        return self._messages


class _LLM:
    _caller_language_supported_codes = {"en", "hi"}

    def __init__(self):
        self.pushed_frames = []

    async def push_frame(self, frame, direction=FrameDirection.DOWNSTREAM):
        self.pushed_frames.append((frame, direction))


def test_phone_confirmation_is_committed_once_and_prompt_moves_to_next_booking_detail():
    context = _Context([
        {"role": "user", "content": "I want to book an appointment"},
        {"role": "assistant", "content": "I heard the number ending in 0941. Is that right?"},
        {"role": "user", "content": "Yes, correct"},
    ])
    llm = _LLM()
    llm._contact_conversation_state = {
        "caller_phone_confirmation_pending": "9538300941",
        "awaiting_phone": True,
    }
    policy_state = CallerContextPolicyState()
    processor = CallerContextPolicyProcessor(llm, policy_state)

    asyncio.run(processor._prepare_context(LLMContextFrame(context=context)))

    assert llm._contact_conversation_state["caller_phone"] == "9538300941"
    assert "caller_phone_confirmation_pending" not in llm._contact_conversation_state
    policy = next(message["content"] for message in context.get_messages() if message.get("role") == "system")
    assert "Do not ask them to confirm or repeat it again" in policy
    assert "What date and time would you prefer" in policy
    policy_state.remove()
    assert context.get_messages()[-1]["content"] == "Yes, correct"


def test_number_correction_keeps_the_latest_pending_capture():
    context = _Context([
        {"role": "assistant", "content": "I heard the number ending in 0941. Is that right?"},
        {"role": "user", "content": "No, nine five three eight three double zero nine four two"},
    ])
    llm = _LLM()
    llm._contact_conversation_state = {
        "caller_phone_confirmation_pending": "9538300941",
        "awaiting_phone": True,
    }
    processor = CallerContextPolicyProcessor(llm, CallerContextPolicyState())

    asyncio.run(processor._prepare_context(LLMContextFrame(context=context)))

    state = llm._contact_conversation_state
    assert state.get("caller_phone") != "9538300941"
    assert state.get("replace_phone_digits_on_next_turn") is True
    assert state.get("awaiting_phone") is True


def test_existing_name_phone_and_date_time_stay_available_after_history_compaction():
    context = _Context([{"role": "user", "content": "My name is Adarsh"}])
    llm = _LLM()
    llm._contact_conversation_state = {
        "caller_name": "Adarsh",
        "caller_phone": "9538300941",
        "prior_booking_request": "I want to book an appointment",
        "recent_caller_statements": ["I want an appointment tomorrow at eight AM"],
    }
    processor = CallerContextPolicyProcessor(llm, CallerContextPolicyState())

    asyncio.run(processor._prepare_context(LLMContextFrame(context=context)))

    policy = next(message["content"] for message in context.get_messages() if message.get("role") == "system")
    assert '"name": "Adarsh"' in policy
    assert '"phone": "9538300941"' in policy
    assert "tomorrow at eight AM" in policy


def test_unsupported_language_request_does_not_change_reply_language():
    context = _Context([{"role": "user", "content": "Please reply in Urdu"}])
    llm = _LLM()
    llm._contact_conversation_state = {"reply_language": "Hindi"}
    processor = CallerContextPolicyProcessor(llm, CallerContextPolicyState())

    asyncio.run(processor._prepare_context(LLMContextFrame(context=context)))

    policy = next(message["content"] for message in context.get_messages() if message.get("role") == "system")
    assert llm._contact_conversation_state["reply_language"] == "Hindi"
    assert "caller explicitly requested Urdu" not in policy


def test_missing_tools_context_does_not_crash_or_assume_booking_capability():
    context = _Context([{"role": "user", "content": "Hello"}])
    del context.tools
    llm = _LLM()
    processor = CallerContextPolicyProcessor(llm, CallerContextPolicyState())

    asyncio.run(processor._prepare_context(LLMContextFrame(context=context)))

    assert context.get_messages()[0]["role"] == "system"
    assert "book an appointment" not in llm._contact_conversation_state


def test_combined_relative_date_and_eight_am_overrides_stale_slot():
    context = _Context([
        {"role": "user", "content": "I want to book an appointment"},
        {"role": "assistant", "content": "I can book that for 7 PM."},
        {"role": "user", "content": "Tomorrow at eight AM"},
    ])
    llm = _LLM()
    llm._known_contact = {"customer_name": "Adarsh", "customer_phone": "9538300941"}
    llm._contact_conversation_state = {
        "caller_name": "Adarsh",
        "caller_phone": "9538300941",
        "booking_slot_candidate": "2026-11-10T19:00",
        "recent_caller_statements": [
            "I want to book an appointment",
            "Tomorrow at eight AM",
        ],
    }
    processor = CallerContextPolicyProcessor(llm, CallerContextPolicyState())

    asyncio.run(processor._prepare_context(LLMContextFrame(context=context)))

    assert "at 8:00 AM IST" in processor._direct_reply
    assert "7:00 PM" not in processor._direct_reply
    assert llm._contact_conversation_state.get("booking_confirmation_slot", "").endswith("T08:00")


def test_compacted_booking_request_preserves_tomorrow_date_and_asks_only_for_time():
    context = _Context([{"role": "user", "content": "Tomorrow"}])
    llm = _LLM()
    llm._known_contact = {"customer_name": "Adarsh", "customer_phone": "9538300941"}
    llm._contact_conversation_state = {
        "caller_name": "Adarsh",
        "caller_phone": "9538300941",
        "recent_caller_statements": ["I want to book an appointment", "Tomorrow"],
    }
    processor = CallerContextPolicyProcessor(llm, CallerContextPolicyState())

    asyncio.run(processor._prepare_context(LLMContextFrame(context=context)))

    assert "What time works for you?" in processor._direct_reply
    assert llm._contact_conversation_state["booking_time_pending"] is True


def test_explicit_english_switch_is_not_overwritten_by_last_hindi_stt_label():
    class _HindiRecognitionSource:
        latest_tts_language = "Hindi"

        async def select_caller_language(self, language):
            assert language == "English"
            return True

    context = _Context([{"role": "user", "content": "Please reply in English"}])
    llm = _LLM()
    llm._caller_language_source = _HindiRecognitionSource()
    llm._contact_conversation_state = {}
    processor = CallerContextPolicyProcessor(llm, CallerContextPolicyState())

    asyncio.run(processor._prepare_context(LLMContextFrame(context=context)))

    assert llm._contact_conversation_state["reply_language"] == "English"
    assert processor._direct_reply == "Yes, we can continue in English."


def test_phone_confirmation_uses_shared_direct_reply_instead_of_calling_provider():
    context = _Context([
        {"role": "user", "content": "I want to book an appointment"},
        {"role": "assistant", "content": "Is the number ending in 0941 correct?"},
        {"role": "user", "content": "Yes, correct"},
    ])
    llm = _LLM()
    llm._contact_conversation_state = {
        "caller_phone_confirmation_pending": "9538300941",
        "awaiting_phone": True,
    }
    processor = CallerContextPolicyProcessor(llm, CallerContextPolicyState())

    asyncio.run(processor.process_frame(
        LLMContextFrame(context=context), FrameDirection.DOWNSTREAM
    ))

    frames = [frame for frame, _ in llm.pushed_frames]
    assert [type(frame) for frame in frames] == [
        LLMFullResponseStartFrame, LLMTextFrame, LLMFullResponseEndFrame,
    ]
    assert frames[1].text == "Thanks. What date and time would you prefer for the booking?"
    assert "caller_phone" in llm._contact_conversation_state


def test_shared_booking_intake_is_direct_for_every_cascade_provider():
    context = _Context([{"role": "user", "content": "I want to book an appointment"}])
    llm = _LLM()
    llm._contact_conversation_state = {}
    processor = CallerContextPolicyProcessor(llm, CallerContextPolicyState())

    asyncio.run(processor.process_frame(
        LLMContextFrame(context=context), FrameDirection.DOWNSTREAM
    ))

    frames = [frame for frame, _ in llm.pushed_frames]
    assert len(frames) == 3
    assert isinstance(frames[1], LLMTextFrame)
    assert "name" in frames[1].text.casefold()
