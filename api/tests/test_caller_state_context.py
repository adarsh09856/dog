from api.services.pipecat.caller_state_context import CallerStateContext


def test_caller_state_prefix_snapshots_survive_service_reconstruction():
    checkpoint = {}
    first = CallerStateContext(checkpoint)
    messages = [
        {"role": "user", "content": "I need an appointment."},
        {"role": "assistant", "content": "What is your name?"},
        {"role": "user", "content": "My name is Ravi."},
    ]
    decorated = first.apply(messages, "Caller name: Ravi")
    assert decorated[2] == {"role": "system", "content": "Caller name: Ravi"}

    # The next HTTP turn creates a new LLM service and context helper.
    second = CallerStateContext(checkpoint)
    followup = [*messages, {"role": "assistant", "content": "What is your phone?"},
                {"role": "user", "content": "Nine five three..."}]
    next_decorated = second.apply(followup, "Caller name: Ravi; phone digits incomplete")
    assert next_decorated[2] == decorated[2]
    assert next_decorated[5] == {"role": "system", "content": "Caller name: Ravi; phone digits incomplete"}


def test_caller_state_prefix_discards_snapshots_after_history_edit():
    checkpoint = {}
    first = CallerStateContext(checkpoint)
    first.apply([{"role": "user", "content": "one"}], "fact one")
    second = CallerStateContext(checkpoint)
    result = second.apply([{"role": "user", "content": "replaced"}], "fact two")
    assert result == [
        {"role": "system", "content": "fact two"},
        {"role": "user", "content": "replaced"},
    ]
    assert checkpoint["users"] == ["replaced"]
