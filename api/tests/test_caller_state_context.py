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
