from api.services.pipecat.caller_state_context import CallerStateContext


def test_caller_state_prefix_snapshots_survive_service_reconstruction():
    checkpoint = {}
    first = CallerStateContext(checkpoint)
    initial = [{"role": "user", "content": "My name is Adarsh."}]
    first.apply(initial, "Caller name is Adarsh.")

    second = CallerStateContext(checkpoint)
    followup = [
        *initial,
        {"role": "assistant", "content": "How can I help?"},
        {"role": "user", "content": "I need an appointment."},
    ]
    result = second.apply(followup, "Caller name is Adarsh.")

    assert result[0] == {
        "role": "system", "content": "Caller name is Adarsh."
    }
    assert result[1:] == followup
    assert checkpoint["users"] == ["My name is Adarsh.", "I need an appointment."]

    # Later turns rebuild the service, so the checkpoint must carry prefixes.
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
    first.apply([{"role": "user", "content": "My name is Adarsh."}], "Caller name is Adarsh.")

    second = CallerStateContext(checkpoint)
    edited = [{"role": "user", "content": "My name is Rohan."}]
    result = second.apply(edited, "Caller name is Rohan.")

    assert result == [
        {"role": "system", "content": "Caller name is Rohan."},
        *edited,
    ]
    assert checkpoint["users"] == ["My name is Rohan."]
    assert checkpoint["snapshots"] == {"0": "Caller name is Rohan."}

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
