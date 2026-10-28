from api.services.workflow.contact_context import caller_phone_fragment_reply


def test_revisiting_same_phone_fragment_does_not_append_it_twice():
    state = {"awaiting_phone": True}
    messages = [{"role": "user", "content": "nine five three"}]

    reply = caller_phone_fragment_reply(messages, state)
    assert reply
    assert state["caller_phone_digits"] == "953"

    assert caller_phone_fragment_reply(messages, state) is None
    assert state["caller_phone_digits"] == "953"


def test_plus_separator_and_double_digit_are_parsed_in_phone_context():
    state = {"awaiting_phone": True}
    messages = [{
        "role": "user",
        "content": "plus nine one nine five three eight three double zero nine four one",
    }]

    assert caller_phone_fragment_reply(messages, state) is None
    assert state["caller_phone"] == "919538300941"


def test_noisy_numeric_phone_answer_gets_retry_instead_of_falling_through():
    state = {"awaiting_phone": True}
    messages = [{
        "role": "user",
        "content": "Nine-five pre-ed pre-double-zero-nine-four-one.",
    }]

    reply = caller_phone_fragment_reply(messages, state)
    assert reply and "repeat the full phone number" in reply
    assert "caller_phone" not in state

