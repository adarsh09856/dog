"""Request construction regressions; no model, database or booking calls."""

from copy import deepcopy
from types import SimpleNamespace

from api.services.pipecat.booking_tool_choice import BookingOpenAILLMService
from pipecat.services.openai.base_llm import OpenAILLMSettings


def service():
    result = BookingOpenAILLMService(
        api_key="test", settings=OpenAILLMSettings(model="qwen3.5:2b")
    )
    result._kodewaves_local_ollama = True
    result._contact_conversation_state = {"caller_name": "Test Caller"}
    return result


def request():
    return {"messages": [
        {"role": "system", "content": "Help with account and order questions."},
        {"role": "user", "content": "Please check my order status."},
    ], "tools": []}


def followup(data, text="Order reference AB123."):
    data["messages"].extend([
        {"role": "assistant", "content": "What is your order reference?"},
        {"role": "user", "content": text},
    ])


def reminders(messages):
    return [m for m in messages if m.get("role") == "system"
            and m.get("content", "").startswith("Caller-provided details")]


def test_unchanged_contact_keeps_entire_previous_request_prefix():
    s, data = service(), request()
    first = s.build_chat_completion_params(data)["messages"]
    followup(data)
    original = deepcopy(data)
    second = s.build_chat_completion_params(data)["messages"]
    assert second[:len(first)] == first
    assert len(reminders(second)) == 1
    assert data == original
    assert s.build_chat_completion_params(data)["messages"] == second


def test_correction_adds_latest_state_without_rewriting_earlier_turn():
    s, data = service(), request()
    first = s.build_chat_completion_params(data)["messages"]
    followup(data, "Actually, my name is New Caller.")
    s._contact_conversation_state["caller_name"] = "New Caller"
    second = s.build_chat_completion_params(data)["messages"]
    assert second[:len(first)] == first
    assert len(reminders(second)) == 2
    assert '"name": "New Caller"' in second[-2]["content"]
    assert s.build_chat_completion_params(data)["messages"] == second


def test_pruned_history_reanchors_current_state_and_discards_old_snapshot():
    s, data = service(), request()
    s.build_chat_completion_params(data)
    s._contact_conversation_state["caller_name"] = "New Caller"
    data["messages"][-1]["content"] = "Check another order."
    result = s.build_chat_completion_params(data)["messages"]
    assert len(reminders(result)) == 1
    assert "Test Caller" not in str(result)
    assert '"name": "New Caller"' in result[-2]["content"]


def test_reset_contact_drops_request_only_reminders():
    s, data = service(), request()
    s.build_chat_completion_params(data)
    s._contact_conversation_state.clear()
    followup(data)
    assert reminders(s.build_chat_completion_params(data)["messages"]) == []


def test_separate_call_does_not_inherit_contact_snapshots():
    s, data = service(), request()
    s.build_chat_completion_params(data)
    other = service()
    other._contact_conversation_state.clear()
    assert reminders(other.build_chat_completion_params(data)["messages"]) == []


def test_tool_continuation_preserves_snapshot_and_tool_messages():
    s, data = service(), request()
    first = s.build_chat_completion_params(data)["messages"]
    data["messages"].extend([
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": "call_test", "type": "function",
            "function": {"name": "lookup_order", "arguments": "{}"},
        }]},
        {"role": "tool", "tool_call_id": "call_test", "content": "Order pending."},
    ])
    second = s.build_chat_completion_params(data)["messages"]
    assert second[:len(first)] == first
    assert second[-2:] == data["messages"][-2:]
    assert len(reminders(second)) == 1


def test_contact_snapshot_survives_hindi_to_english_reply_switch():
    s, data = service(), request()
    data["messages"][-1]["content"] = "मुझे अपने ऑर्डर की जानकारी चाहिए।"
    source = SimpleNamespace(
        latest_detected_language="hi",
        latest_detected_text=data["messages"][-1]["content"],
    )
    s._caller_language_source = source
    first = s.build_chat_completion_params(data)["messages"]
    followup(data, "Please explain in English.")
    source.latest_detected_language = "en"
    source.latest_detected_text = data["messages"][-1]["content"]
    original = deepcopy(data)
    second = s.build_chat_completion_params(data)["messages"]
    assert second[:len(first)] == first
    assert "English" in second[-1]["content"]
    assert len(reminders(second)) == 1
    assert data == original
