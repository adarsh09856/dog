from datetime import datetime, timezone

from api.services.pipecat.booking_tool_choice import BookingOpenAILLMService
from pipecat.services.openai.base_llm import OpenAILLMSettings


def test_current_date_request_gets_a_live_india_clock_without_mutating_history():
    from api.services.pipecat.runtime_clock_context import add_current_clock

    original = [{"role": "system", "content": "Help with orders."},
                {"role": "user", "content": "What is today's date?"}]
    result = add_current_clock(original, now=datetime(2026, 10, 27, 20, 0, tzinfo=timezone.utc))
    assert "2026-10-28" in result[-2]["content"]
    assert "Asia/Kolkata" in result[-2]["content"]
    assert result[-1] == original[-1]
    assert len(original) == 2


def test_hindi_hinglish_and_english_clock_questions_get_context():
    from api.services.pipecat.runtime_clock_context import add_current_clock

    for text in ("आज की तारीख क्या है?", "अभी कितने बजे हैं?", "Aaj ki date kya hai?", "What time is it now?"):
        request = [{"role": "user", "content": text}]
        assert len(add_current_clock(request)) == 2


def test_no_clock_is_inserted_for_unrelated_turn_or_tool_result():
    from api.services.pipecat.runtime_clock_context import add_current_clock

    for history in (
        [{"role": "user", "content": "My order arrived today."}],
        [{"role": "user", "content": "What is my order status now?"}],
        [{"role": "user", "content": "What is today's date?"},
         {"role": "tool", "content": "A result"}],
        [{"role": "assistant", "content": "What time is it now?"}],
    ):
        assert add_current_clock(history) == history


def test_non_indian_timezone_is_not_misrepresented_as_ist():
    from api.services.pipecat.runtime_clock_context import add_current_clock

    for text in ("What time is it in New York?", "What is the date in London?", "What is the date in UTC?", "What time is it in Paris?"):
        history = [{"role": "user", "content": text}]
        assert add_current_clock(history) == history


def test_real_llm_request_builder_includes_clock_for_generic_workflow():
    from copy import deepcopy

    service = BookingOpenAILLMService(api_key="test", settings=OpenAILLMSettings(model="qwen3.5:2b"))
    service._kodewaves_local_ollama = True
    request = {"messages": [{"role": "system", "content": "Help with orders."},
                            {"role": "user", "content": "What is today's date?"}], "tools": []}
    original = deepcopy(request)
    result = service.build_chat_completion_params(request)["messages"]
    assert any("Current India local time:" in m.get("content", "") for m in result)
    assert "Reply in English" in result[-1]["content"]
    assert result[-1]["content"].endswith(request["messages"][-1]["content"])
    assert request == original
    assert len(request["messages"]) == 2


def test_local_clock_keeps_system_and_prior_turn_stable_across_midnight():
    from copy import deepcopy
    from api.services.pipecat.runtime_clock_context import CallerClockContext

    system = {"role": "system", "content": (
        "Book only with consent.\n\nCurrent India local time: 2026-10-27T23:59+05:30 "
        "(IST, Asia/Kolkata). Interpret dates and times as India local time. "
        "Use another timezone only when the caller explicitly requests one. "
        "Never invent the current date."
    )}
    first = [system, {"role": "user", "content": "I need an appointment."}]
    original = deepcopy(first)
    clock = CallerClockContext()
    before = clock.apply(first, now=datetime(2026, 10, 27, 18, 29, tzinfo=timezone.utc))
    second = [*first, {"role": "assistant", "content": "Which date?"},
              {"role": "user", "content": "Tomorrow."}]
    after = clock.apply(second, now=datetime(2026, 10, 27, 18, 31, tzinfo=timezone.utc))
    assert before == after[:len(before)]
    assert "2026-10-28T00:01+05:30" in after[-2]["content"]
    assert "2026-10-27T23:59+05:30" in after[1]["content"]
    assert "2026" not in before[0]["content"]
    assert first == original


def test_local_clock_checkpoint_restores_prior_clocks_for_text_chat():
    import json
    from api.services.pipecat.runtime_clock_context import CallerClockContext

    state = {}
    first = [{"role": "user", "content": "What time is it now?"}]
    before = CallerClockContext(state).apply(first, now=datetime(2026, 10, 27, 18, 0, tzinfo=timezone.utc))
    restored = json.loads(json.dumps(state))
    after = CallerClockContext(restored).apply(
        [*first, {"role": "assistant", "content": "It is 11:30 pm."},
         {"role": "user", "content": "What time is it now?"}],
        now=datetime(2026, 10, 27, 18, 1, tzinfo=timezone.utc),
    )
    assert before == after[:len(before)]
    assert "23:31" in after[-2]["content"]
    assert "What time" not in json.dumps(state)


def test_local_clock_does_not_decorate_tools_or_unrelated_generic_turns():
    from api.services.pipecat.runtime_clock_context import CallerClockContext

    for messages in (
        [{"role": "user", "content": "Help me with my order."}],
        [{"role": "user", "content": "What time is it in London?"}],
        [{"role": "tool", "content": "What time is it now?"}],
    ):
        assert CallerClockContext().apply(messages) == messages


def test_local_clock_discards_snapshots_when_history_is_replaced():
    from api.services.pipecat.runtime_clock_context import CallerClockContext

    clock = CallerClockContext()
    clock.apply([{"role": "user", "content": "What time is it now?"}])
    fresh = [{"role": "user", "content": "A different conversation."}]
    assert clock.apply(fresh) == fresh


def test_real_local_builder_preserves_previous_request_after_clock_changes():
    from copy import deepcopy
    from types import SimpleNamespace
    from unittest.mock import patch
    import api.services.pipecat.runtime_clock_context as clock_module

    service = BookingOpenAILLMService(api_key="test", settings=OpenAILLMSettings(model="qwen3.5:2b"))
    service._kodewaves_local_ollama = True
    service._contact_conversation_state = {}
    system = {"role": "system", "content": (
        "Current India local time: 2026-10-27T23:59+05:30 "
        "(IST, Asia/Kolkata). Interpret dates and times as India local time. "
        "Use another timezone only when the caller explicitly requests one. "
        "Never invent the current date."
    )}
    first = [system, {"role": "user", "content": "मुझे मदद चाहिए।"}]
    original = deepcopy(first)
    source = SimpleNamespace(latest_detected_language="hi", latest_detected_text=first[-1]["content"])
    service._caller_language_source = source
    with patch.object(clock_module, "datetime") as clock:
        clock.now.return_value = datetime(2026, 10, 27, 18, 29, tzinfo=timezone.utc).astimezone(clock_module.ZoneInfo("Asia/Kolkata"))
        before = service.build_chat_completion_params({"messages": first, "tools": []})["messages"]
        second = [*first, {"role": "assistant", "content": "किस काम में?"},
                  {"role": "user", "content": "मुझे कल मिलना है।"}]
        source.latest_detected_text = second[-1]["content"]
        clock.now.return_value = datetime(2026, 10, 27, 18, 31, tzinfo=timezone.utc).astimezone(clock_module.ZoneInfo("Asia/Kolkata"))
        after = service.build_chat_completion_params({"messages": second, "tools": []})["messages"]
    assert before == after[:len(before)]
    assert "2026-10-28T00:01+05:30" in str(after[len(before):])
    assert first == original
    assert service._contact_conversation_state["_runtime_clock_context"]["snapshots"]
