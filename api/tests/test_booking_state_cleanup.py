import ast
from pathlib import Path

import pytest

from api.services.workflow.contact_context import (
    caller_state_instruction,
    clear_completed_booking_state,
    remember_recent_caller_statements,
)


@pytest.fixture
def booking_state():
    return {
        "booking_confirmation_slot": "2035-10-20T10:00",
        "booking_time_question_date": "2035-10-20",
        "prior_booking_request": "Book a room for October 20",
        "active_booking_request": "legacy request",
        "recent_caller_statements": ["Book a room", "October 20, 2035"],
        "caller_name": "Asha",
        "caller_phone": "+919876543210",
        "caller_phone_digits": "9876543210",
        "caller_phone_confirmation_pending": True,
    }


def test_persisted_booking_clears_only_staged_and_historical_booking_state(booking_state):
    clear_completed_booking_state(
        booking_state,
        {"booked": True, "appointment_id": "saved-123"},
        [
            {"role": "user", "id": "request-1", "content": "Book an appointment October 20"},
            {"role": "assistant", "content": "October 20, 10 AM. Should I book the appointment?"},
            {"role": "user", "id": "confirm-2", "content": "Yes"},
        ],
    )

    assert "booking_confirmation_slot" not in booking_state
    assert "booking_time_question_date" not in booking_state
    assert "prior_booking_request" not in booking_state
    assert "active_booking_request" not in booking_state
    assert "recent_caller_statements" not in booking_state
    assert booking_state["_completed_booking_turn_boundary"]["identities"][0] == {
        "kind": "id", "value": "confirm-2"
    }
    assert booking_state["caller_name"] == "Asha"
    assert booking_state["caller_phone"] == "+919876543210"
    assert booking_state["caller_phone_digits"] == "9876543210"
    assert booking_state["caller_phone_confirmation_pending"] is True


@pytest.mark.parametrize(
    "result", [{"booked": False, "status": "error"}, {"booked": False, "status": "conflict"}, {}]
)
def test_failed_or_conflicting_booking_preserves_staged_and_retry_state(booking_state, result):
    original = dict(booking_state)

    clear_completed_booking_state(booking_state, result)

    assert booking_state == original


def test_success_boundary_prevents_old_booking_and_date_from_rehydrating_but_allows_rebooking(
    booking_state,
):
    transcript = [
        {"role": "user", "id": "old-request", "content": "I need to book an appointment October 20"},
        {"role": "assistant", "content": "October 20 at 10 AM. Should I book the appointment?"},
        {"role": "user", "id": "old-confirm", "content": "Yes"},
    ]
    clear_completed_booking_state(
        booking_state,
        {"booked": True, "appointment_id": "saved-123"},
        transcript,
    )

    ordinary_turn = {"role": "user", "id": "ordinary-1", "content": "Can you help with my address?"}
    transcript.append(ordinary_turn)
    remember_recent_caller_statements(transcript, booking_state)

    assert "prior_booking_request" not in booking_state
    assert booking_state["recent_caller_statements"] == [ordinary_turn["content"]]
    reminder = caller_state_instruction(booking_state)
    assert reminder is not None
    assert "October 20" not in reminder

    repeated_request = {
        "role": "user",
        "id": "new-request",
        "content": "I need to book an appointment October 20",
    }
    transcript.append(repeated_request)
    remember_recent_caller_statements(transcript, booking_state)
    assert booking_state["prior_booking_request"] == repeated_request["content"]
    assert booking_state["recent_caller_statements"] == [
        ordinary_turn["content"], repeated_request["content"]
    ]


def test_success_boundary_matches_existing_fallback_identity_when_ids_are_compacted():
    state = {}
    transcript = [
        {"role": "user", "id": "req", "content": "Book an appointment October 20"},
        {"role": "assistant", "content": "Should I book the appointment for that time?"},
        {"role": "user", "id": "yes", "content": "Yes"},
    ]
    clear_completed_booking_state(
        state, {"booked": True, "appointment_id": "saved-123"}, transcript
    )
    compacted = [
        {key: value for key, value in message.items() if key != "id"}
        for message in transcript
    ]
    compacted.append({"role": "user", "content": "What is your address?"})

    remember_recent_caller_statements(compacted, state)

    assert "prior_booking_request" not in state
    assert state["recent_caller_statements"] == ["What is your address?"]


def test_stable_confirmation_id_wins_over_an_earlier_identical_fallback_turn():
    state = {}
    transcript = [
        {"role": "assistant", "content": "Should I book the appointment for that time?"},
        {"role": "user", "id": "earlier-yes", "content": "Yes"},
        {"role": "user", "id": "new-booking", "content": "Book another appointment October 30"},
        {"role": "assistant", "content": "Should I book the appointment for that time?"},
        {"role": "user", "id": "saved-yes", "content": "Yes"},
    ]
    clear_completed_booking_state(
        state, {"booked": True, "appointment_id": "saved-123"}, transcript
    )
    transcript.append({"role": "user", "id": "ordinary", "content": "What is your address?"})

    remember_recent_caller_statements(transcript, state)

    assert "prior_booking_request" not in state
    assert state["recent_caller_statements"] == ["What is your address?"]


def _function_node(tree: ast.AST, name: str) -> ast.FunctionDef:
    return next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def test_text_chat_and_pipecat_booking_paths_both_use_success_gated_cleanup():
    root = Path(__file__).parents[1] / "services" / "workflow"
    text_tree = ast.parse((root / "text_chat_runner.py").read_text(encoding="utf-8"))
    pipecat_tree = ast.parse(
        (root / "pipecat_engine_custom_tools.py").read_text(encoding="utf-8")
    )

    text_turn = _function_node(text_tree, "execute_text_chat_pending_turn")
    booking_handler = _function_node(pipecat_tree, "booking_handler")
    for path_node in (text_turn, booking_handler):
        assert any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "clear_completed_booking_state"
            for node in ast.walk(path_node)
        )
