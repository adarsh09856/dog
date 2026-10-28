from api.services.pipecat.booking_tool_choice import BookingOpenAILLMService, booking_tool_choice
from pipecat.services.openai.base_llm import OpenAILLMSettings
from unittest.mock import AsyncMock
from types import SimpleNamespace
import pytest
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.adapters.schemas.function_schema import FunctionSchema


TOOL = {"type": "function", "function": {"name": "book_appointment", "parameters": {"type": "object"}}}


def _params(*messages, tools=None):
    return {"messages": list(messages), "tools": [TOOL] if tools is None else tools}


@pytest.mark.parametrize('model', ['gpt-4o-mini', 'qwen3.5:2b'])
def test_request_routing_guards_preserve_reusable_conversation_context(model):
    from copy import deepcopy

    service = BookingOpenAILLMService(api_key='test', settings=OpenAILLMSettings(model=model))
    context = _params(
        {'role': 'system', 'content': 'Support assistant.\n\nWorkflow step routing: Follow the matching route.\n- assist_caller: Continue to support.'},
        {'role': 'assistant', 'content': 'Hello. How can I help?'},
        {'role': 'system', 'content': 'Continue the existing conversation after a brief idle period.'},
        {'role': 'user', 'content': 'Can you help with my account?'},
        tools=[{'type': 'function', 'function': {'name': 'assist_caller', 'parameters': {'type': 'object'}}}],
    )
    original = deepcopy(context)
    first = service.build_chat_completion_params(context)
    assert context == original
    second = service.build_chat_completion_params(context)
    assert context == original
    assert first['messages'] == second['messages']
    assert 'assist_caller:' in context['messages'][0]['content']
    assert any('assist_caller:' in message.get('content', '') for message in first['messages'])


def test_detected_whisper_language_is_request_only_and_not_reused_for_idle_text():
    service = BookingOpenAILLMService(
        api_key='test', settings=OpenAILLMSettings(model='qwen3.5:2b')
    )
    service._caller_language_source = SimpleNamespace(
        latest_detected_language='en', latest_detected_text='I need account help'
    )
    request = _params(
        {'role': 'system', 'content': 'Hindi-speaking assistant.'},
        {'role': 'user', 'content': 'I need account help'}, tools=[]
    )
    prepared = service.build_chat_completion_params(request)
    assert 'Answer in English' in prepared['messages'][-1]['content']
    assert request['messages'][-1]['content'] == 'I need account help'

    idle = _params({'role': 'user', 'content': 'Are you still there?'}, tools=[])
    assert service.build_chat_completion_params(idle)['messages'][-1]['content'] == 'Are you still there?'


def test_local_qwen_keeps_response_guard_in_reusable_prefix_without_mutating_history():
    from copy import deepcopy
    from api.services.pipecat.booking_tool_choice import _LOCAL_CALLER_RESPONSE_GUARD

    service = BookingOpenAILLMService(
        api_key="test", settings=OpenAILLMSettings(model="qwen3.5:2b")
    )
    service._kodewaves_local_ollama = True
    request = _params(
        {"role": "system", "content": "Ask callers which department they need."},
        {"role": "assistant", "content": "नमस्ते। कैसे मदद करूँ?"},
        {"role": "user", "content": "मुझे रूम बुक करना है"},
        tools=[],
    )
    original = deepcopy(request["messages"])

    prepared = service.build_chat_completion_params(request)

    assert request["messages"] == original
    guard_index = next(
        i for i, message in enumerate(prepared["messages"])
        if message.get("role") == "system"
        and message.get("content") == _LOCAL_CALLER_RESPONSE_GUARD
    )
    assert guard_index == 1
    guard = prepared["messages"][guard_index]["content"]
    assert "warm, constructive tone" in guard
    assert "Never claim a booking or other action succeeded" in guard
    assert "not verified" in guard
    assert "Answer the latest caller message directly" in guard
    assert "Do not repeat the caller's words" in guard
    assert "Never invent service names" in guard
    assert "carry forward every date, service, and time" in guard
    assert "do not restart the booking questions" in guard

    followup = deepcopy(request)
    followup["messages"].extend([
        {"role": "assistant", "content": "नया पता क्या है?"},
        {"role": "user", "content": "बेंगलुरु"},
    ])
    prepared_followup = service.build_chat_completion_params(followup)["messages"]
    assert prepared_followup[:len(prepared["messages"])] == prepared["messages"]
    assert sum(
        message.get("role") == "system"
        and message.get("content") == _LOCAL_CALLER_RESPONSE_GUARD
        for message in prepared_followup
    ) == 1
    assert followup["messages"] == request["messages"] + [
        {"role": "assistant", "content": "नया पता क्या है?"},
        {"role": "user", "content": "बेंगलुरु"},
    ]


def test_local_qwen_gets_validated_caller_details_before_the_latest_turn():
    from copy import deepcopy

    service = BookingOpenAILLMService(
        api_key="test", settings=OpenAILLMSettings(model="qwen3.5:2b")
    )
    service._kodewaves_local_ollama = True
    service._contact_conversation_state = {
        "caller_name": "आदर्श",
        "caller_phone": "9538300941",
    }
    request = _params(
        {"role": "system", "content": "Help the caller book a room."},
        {"role": "assistant", "content": "Please tell me your number."},
        {"role": "user", "content": "નાઇન ફાઇવ த்ரீ ஏஐட் த்ரீ டபுள் ஜીરோ"},
        tools=[],
    )
    original = deepcopy(request["messages"])

    messages = service.build_chat_completion_params(request)["messages"]

    assert request["messages"] == original
    latest_user = max(
        index for index, message in enumerate(messages)
        if message.get("role") == "user"
    )
    reminder = messages[latest_user - 1]
    assert reminder["role"] == "system"
    assert '"phone": "9538300941"' in reminder["content"]
    assert "do not ask for them again" in reminder["content"]


def test_real_request_builder_keeps_recognized_language_prefix_on_followup():
    service = BookingOpenAILLMService(
        api_key='test', settings=OpenAILLMSettings(model='qwen3.5:2b')
    )
    source = SimpleNamespace(latest_detected_language='ta', latest_detected_text='எனக்கு உதவி வேண்டும்')
    service._caller_language_source = source
    request = _params(
        {'role': 'system', 'content': 'Assist callers.'},
        {'role': 'assistant', 'content': 'Hello. How can I help?'},
        {'role': 'user', 'content': source.latest_detected_text}, tools=[]
    )
    first = service.build_chat_completion_params(request)['messages']
    request['messages'].extend([
        {'role': 'assistant', 'content': 'என்ன உதவி வேண்டும்?'},
        {'role': 'user', 'content': 'Please explain in English.'},
    ])
    source.latest_detected_language = 'en'
    source.latest_detected_text = 'Please explain in English.'
    followup = service.build_chat_completion_params(request)['messages']
    assert followup[:len(first)] == first
    assert 'Answer in English' in followup[-1]['content']


def test_explicitly_confirmed_booking_forces_persistence_action():
    params = _params(
        {"role": "assistant", "content": "Your consultation appointment is 15 October at 10:00 AM IST. Confirm?"},
        {"role": "user", "content": "Yes, I confirm this appointment. Please save it."},
    )
    assert booking_tool_choice(params) == {"type": "function", "function": {"name": "book_appointment"}}


def test_booking_action_is_not_forced_without_confirmation_or_tool():
    user = {"role": "user", "content": "I want a booking next week."}
    assert booking_tool_choice(_params(user)) is None
    assert booking_tool_choice(_params({"role": "user", "content": "I confirm my appointment"}, tools=[])) is None


def test_booking_action_is_not_forced_for_cancellation_or_tool_result():
    assert booking_tool_choice(_params({"role": "user", "content": "Do not save my appointment now"})) is None
    assert booking_tool_choice(_params({"role": "tool", "content": '{"booked": false}'})) is None


def test_collection_turn_hides_booking_but_keeps_routing_tools_available():
    service = BookingOpenAILLMService(api_key='test', settings=OpenAILLMSettings(model='qwen3:1.7b'))
    route = {'type': 'function', 'function': {'name': 'assist_caller', 'parameters': {'type': 'object'}}}
    params = service.build_chat_completion_params(_params(
        {'role': 'user', 'content': 'main appointment book karna chahta hu'}, tools=[TOOL, route]))
    assert [tool['function']['name'] for tool in params['tools']] == ['assist_caller']


def test_unconfirmed_turn_with_only_booking_has_no_invalid_required_tool_choice():
    service = BookingOpenAILLMService(api_key='test', settings=OpenAILLMSettings(model='qwen3:1.7b'))
    params = service.build_chat_completion_params({**_params(
        {'role': 'user', 'content': 'What appointment times are available?'}), 'tool_choice': 'required'})
    assert 'tools' not in params and 'tool_choice' not in params


def test_yes_after_readback_preserves_booking_action():
    service = BookingOpenAILLMService(api_key='test', settings=OpenAILLMSettings(model='qwen3:1.7b'))
    params = service.build_chat_completion_params(_params(
        {'role': 'assistant', 'content': 'Your appointment is tomorrow at 10 AM IST. Is this correct?'},
        {'role': 'user', 'content': 'Yes.'}))
    assert params['tools'][0]['function']['name'] == 'book_appointment'
    assert params['tool_choice']['function']['name'] == 'book_appointment'


def test_openai_compatible_runtime_sends_required_booking_tool_choice():
    service = BookingOpenAILLMService(
        api_key="test", base_url="http://localhost:11434/v1",
        settings=OpenAILLMSettings(model="qwen2.5:1.5b"),
    )
    params = service.build_chat_completion_params(_params(
        {"role": "assistant", "content": "Your appointment is 15 October at 10:00 IST. Confirm?"},
        {"role": "user", "content": "I confirm this appointment. Save it."},
    ))
    assert params["tool_choice"]["function"]["name"] == "book_appointment"
    assert [tool['function']['name'] for tool in params['tools']] == ['book_appointment']
    assert 'do not greet again' in params['messages'][-1]['content']


def test_llm_client_has_a_bounded_timeout_and_no_silent_retries():
    service = BookingOpenAILLMService(
        api_key="test", base_url="http://localhost:11434/v1",
        settings=OpenAILLMSettings(model="qwen3:1.7b"),
    )
    assert service._client.max_retries == 0
    assert service._client.timeout.read == 45.0


def test_first_reply_does_not_replay_configured_hindi_greeting():
    service = BookingOpenAILLMService(
        api_key="test", settings=OpenAILLMSettings(model="qwen3:1.7b")
    )
    greeting = "नमस्ते, मैं आशा हूँ। बताइए, मैं आपकी कैसे मदद कर सकती हूँ?"
    params = service.build_chat_completion_params(_params(
        {"role": "system", "content": "Appointment assistant."},
        {"role": "assistant", "content": greeting},
        {"role": "user", "content": "Mujhe appointment book karna hai"},
    ))
    assert all(message.get("content") != greeting for message in params["messages"])
    note = next(message for message in params["messages"] if message.get("role") == "system" and "opening greeting" in message.get("content", ""))
    assert params["messages"].index(note) < next(
        index for index, message in enumerate(params["messages"])
        if message.get("role") == "user"
    )


def test_follow_up_keeps_opening_out_of_prompt_and_preserves_prefix():
    service = BookingOpenAILLMService(
        api_key="test", settings=OpenAILLMSettings(model="qwen3.5:2b")
    )
    greeting = "नमस्ते। बताइए, मैं आपकी किस तरह मदद करूँ?"
    system = {"role": "system", "content": "Answer the latest caller message."}
    first = service.build_chat_completion_params(_params(
        system, {"role": "assistant", "content": greeting},
        {"role": "user", "content": "I need account help."},
    ))["messages"]
    follow_up = service.build_chat_completion_params(_params(
        system, {"role": "assistant", "content": greeting},
        {"role": "user", "content": "I need account help."},
        {"role": "assistant", "content": "Which setting do you want to change?"},
        {"role": "user", "content": "Notifications."},
    ))["messages"]
    assert greeting not in [message.get("content") for message in follow_up]
    assert first[:3] == follow_up[:3]


def test_known_caller_details_do_not_mutate_cached_system_prefix():
    service = BookingOpenAILLMService(
        api_key="test", settings=OpenAILLMSettings(model="qwen3.5:2b")
    )
    stable_system = {"role": "system", "content": "Help the caller book a room."}
    history = [
        stable_system,
        {"role": "user", "content": "I need a room."},
        {"role": "assistant", "content": "What name should I use?"},
        {"role": "user", "content": "My name is Adarsh."},
        {"role": "assistant", "content": "Thanks. What date do you need?"},
        {"role": "user", "content": "Tomorrow."},
    ]

    prepared = service.build_chat_completion_params(_params(*history))["messages"]

    assert prepared[0] == stable_system
    assert not any(
        message.get("role") == "system"
        and "Caller name explicitly provided:" in message.get("content", "")
        for message in prepared
    )
    assert "My name is Adarsh." in [
        message.get("content") for message in prepared if message.get("role") == "user"
    ]


def test_first_caller_reply_preserves_configured_handoff_but_hides_unconfirmed_booking():
    service = BookingOpenAILLMService(
        api_key="test", settings=OpenAILLMSettings(model="qwen3:1.7b")
    )
    route = {"type": "function", "function": {"name": "assist_caller", "parameters": {"type": "object"}}}
    params = service.build_chat_completion_params(_params(
        {"role": "system", "content": "Appointment assistant.\n\nWorkflow step routing: when the condition matches, invoke the transition.\n- assist_caller: Route to the agent node."},
        {"role": "assistant", "content": "नमस्ते, मैं आशा हूँ। बताइए, मैं आपकी कैसे मदद कर सकती हूँ?"},
        {"role": "user", "content": "Hello, are you listening?"},
        tools=[TOOL, route],
    ))
    assert "assist_caller" in [
        tool["function"]["name"] for tool in params.get("tools", [])
    ]
    assert any(
        "assist_caller:" in message.get("content", "")
        for message in params["messages"]
        if message.get("role") == "system"
    )
    assert any(
        "assist_caller:" in message.get("content", "")
        for message in params["messages"]
        if message.get("role") == "system"
    )
    assert params["messages"][-1]["role"] == "user"
    assert not any(
        message.get("role") == "system"
        and "Continue the conversation here" in message.get("content", "")
        for message in params["messages"]
    )
    assert "book_appointment" not in [t["function"]["name"] for t in params.get("tools", [])]


def test_follow_up_turns_preserve_configured_transition_tools():
    service = BookingOpenAILLMService(
        api_key="test", settings=OpenAILLMSettings(model="qwen3:1.7b")
    )
    route = {"type": "function", "function": {"name": "assist_caller", "parameters": {"type": "object"}}}
    params = service.build_chat_completion_params(_params(
        {"role": "system", "content": "Appointment assistant.\n\nWorkflow step routing: when a condition below matches, invoke that transition tool.\n- assist_caller: Hand over to the agent."},
        {"role": "assistant", "content": "नमस्ते, मैं आशा हूँ। बताइए, मैं आपकी कैसे मदद कर सकती हूँ?"},
        {"role": "user", "content": "Hello, are you listening?"},
        {"role": "assistant", "content": "Yes, I am listening."},
        {"role": "user", "content": "I want to book an appointment tomorrow at 10 AM."},
        tools=[TOOL, route],
    ))
    assert "assist_caller" in [
        tool["function"]["name"] for tool in params.get("tools", [])
    ]


def test_end_transition_tool_only_offered_after_clear_farewell():
    service = BookingOpenAILLMService(
        api_key="test", settings=OpenAILLMSettings(model="qwen3:1.7b")
    )
    end_route = {"type": "function", "function": {"name": "finish_call", "parameters": {"type": "object"}}}
    tools = [TOOL, end_route]
    for utterance in ("Hello, are you listening?", "No, I still need help"):
        params = service.build_chat_completion_params(_params(
            {"role": "user", "content": utterance}, tools=tools,
        ))
        assert "finish_call" not in [tool["function"]["name"] for tool in params.get("tools", [])]
    params = service.build_chat_completion_params(_params(
        {"role": "user", "content": "Thanks, goodbye"}, tools=tools,
    ))
    assert "finish_call" in [tool["function"]["name"] for tool in params["tools"]]


@pytest.mark.asyncio
async def test_complete_hindi_confirmation_uses_registered_tool_without_model_request():
    service = BookingOpenAILLMService(api_key='test', settings=OpenAILLMSettings(model='qwen3:1.7b'))
    context = LLMContext(messages=[{'role': 'user', 'content':
        'मैं राहुल अपॉइंटमेंट की पुष्टि करता हूँ। फोन +15555550123 है। '
        '16 अक्टूबर 2026 दोपहर 12:00 बजे UTC+05:30 पर बुक करें।'}],
        tools=ToolsSchema(standard_tools=[FunctionSchema(name='book_appointment', description='Book', properties={}, required=[])]))
    service.run_function_calls = AsyncMock()
    service.get_chat_completions = AsyncMock()
    await service._process_context(context)
    call = service.run_function_calls.call_args.args[0][0]
    assert call.function_name == 'book_appointment'
    assert call.arguments['customer_name'] == 'राहुल'
    service.get_chat_completions.assert_not_awaited()


@pytest.mark.asyncio
async def test_first_booking_question_skips_slow_model_and_uses_normal_speech_frames():
    service = BookingOpenAILLMService(api_key="test", settings=OpenAILLMSettings(model="qwen3.5:2b"))
    context = LLMContext(
        messages=[{"role": "assistant", "content": "नमस्ते, मैं आशा हूँ।"},
                  {"role": "user", "content": "I want to book an appointment tomorrow at 10 AM."}],
        tools=ToolsSchema(standard_tools=[FunctionSchema(name="book_appointment", description="Book", properties={}, required=[])]),
    )
    service.start_ttfb_metrics = AsyncMock()
    service.push_frame = AsyncMock()
    service._push_llm_text = AsyncMock()
    service.get_chat_completions = AsyncMock()

    await service._process_context(context)

    service._push_llm_text.assert_awaited_once_with("Sure. What name should I use for the appointment?")
    service.get_chat_completions.assert_not_awaited()
    service.push_frame.assert_not_awaited()


@pytest.mark.asyncio
async def test_hindi_order_topic_fragment_uses_fast_clarification_with_lookup_tools():
    service = BookingOpenAILLMService(
        api_key="test", settings=OpenAILLMSettings(model="qwen3.5:2b")
    )
    context = LLMContext(
        messages=[
            {"role": "assistant", "content": "नमस्ते। बताइए, मैं आपकी कैसे मदद करूँ?"},
            {"role": "user", "content": "अः मुझे एक ऑर्डर के देकर बात कर"},
        ],
        tools=ToolsSchema(standard_tools=[FunctionSchema(
            name="get_order_status", description="Look up order status",
            properties={"order_id": {"type": "string"}}, required=["order_id"],
        )]),
    )
    service.start_ttfb_metrics = AsyncMock()
    service.push_frame = AsyncMock()
    service._push_llm_text = AsyncMock()
    service.get_chat_completions = AsyncMock()

    await service._process_context(context)

    service._push_llm_text.assert_awaited_once_with("ज़रूर, ऑर्डर में क्या मदद चाहिए?")
    service.get_chat_completions.assert_not_awaited()
    service.push_frame.assert_not_awaited()


@pytest.mark.asyncio
async def test_short_hindi_name_after_combined_contact_question_advances_without_llm():
    service = BookingOpenAILLMService(
        api_key="test", settings=OpenAILLMSettings(model="qwen3.5:2b")
    )
    context = LLMContext(messages=[
        {"role": "assistant", "content": "नया ऑर्डर बनाने के लिए कृपया अपना नाम और मोबाइल नंबर दें।"},
        {"role": "user", "content": "राहुल"},
    ])
    service.start_ttfb_metrics = AsyncMock()
    service.push_frame = AsyncMock()
    service._push_llm_text = AsyncMock()
    service.get_chat_completions = AsyncMock()

    await service._process_context(context)

    service._push_llm_text.assert_awaited_once_with(
        "धन्यवाद, राहुल जी। अब कृपया मोबाइल नंबर बताइए।"
    )
    service.get_chat_completions.assert_not_awaited()
    assert service._contact_conversation_state["caller_name"] == "राहुल"


@pytest.mark.asyncio
async def test_recognized_language_switch_is_applied_without_qwen_and_not_speculated():
    service = BookingOpenAILLMService(api_key="test", settings=OpenAILLMSettings(model="qwen3.5:2b"))
    text = "कन यूताार्क इन इंग्लिश"
    service._caller_language_source = SimpleNamespace(latest_detected_language="hi", latest_detected_text=text)
    service.start_ttfb_metrics = AsyncMock()
    service.push_frame = AsyncMock()
    service._push_llm_text = AsyncMock()
    service.get_chat_completions = AsyncMock()
    assert not service.can_speculate_caller_turn(text)
    await service._process_context(LLMContext(messages=[{"role": "user", "content": text}]))
    service._push_llm_text.assert_awaited_once_with("Yes, we can continue in English.")
    service.get_chat_completions.assert_not_awaited()
    assert service._contact_conversation_state["reply_language"] == "English"


@pytest.mark.asyncio
async def test_contact_question_is_confirmed_before_updating_shared_name_state():
    service = BookingOpenAILLMService(api_key="test", settings=OpenAILLMSettings(model="qwen3.5:2b"))
    messages = [{"role": "assistant", "content": "कृपया अपना नाम और संपर्क विवरण दें।"}]
    state = {}
    service._contact_conversation_state = state
    service._contact_context_messages_provider = lambda: messages
    text = "मेरा नाम आदर्श है मेरा नंबर है तो है"
    assert not service.can_speculate_caller_turn(text)
    assert state == {}
    service.start_ttfb_metrics = AsyncMock()
    service.push_frame = AsyncMock()
    service._push_llm_text = AsyncMock()
    service.get_chat_completions = AsyncMock()
    await service._process_context(LLMContext(messages=[*messages, {"role": "user", "content": text}]))
    assert state["caller_name"] == "आदर्श"
    service.get_chat_completions.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_error_after_tool_dispatch_does_not_ask_caller_to_retry(monkeypatch):
    from pipecat.services.openai.llm import OpenAILLMService

    service = BookingOpenAILLMService(api_key="test", settings=OpenAILLMSettings(model="qwen3.5:2b"))
    service._push_llm_text = AsyncMock()

    async def tool_then_error(self, context):
        self._completion_has_tool_calls = True
        raise TimeoutError("synthetic stream failure after tool dispatch")

    monkeypatch.setattr(OpenAILLMService, "_process_context", tool_then_error)
    with pytest.raises(TimeoutError):
        await service._process_context(LLMContext(messages=[{"role": "user", "content": "What are your hours?"}]))
    service._push_llm_text.assert_not_awaited()
