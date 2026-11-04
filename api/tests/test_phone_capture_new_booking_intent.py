from api.services.workflow.contact_context import caller_phone_fragment_reply
from api.services.workflow.confirmed_booking import first_booking_question


def test_hindi_new_booking_request_exits_pending_phone_capture():
    state = {
        "awaiting_phone": True,
        "caller_phone_digits": "95383",
        "caller_phone_uncertain_one": True,
        "caller_phone_confirmation_pending": "9538300941",
        "caller_phone": "+919876543210",
    }
    messages = [
        {"role": "assistant", "content": "कृपया अपना फ़ोन नंबर बताइए।"},
        {"role": "user", "content": "मुझे कल का एक अपॉइंटमेंट बुक करना था"},
    ]

    assert caller_phone_fragment_reply(messages, state) is None
    assert "awaiting_phone" not in state
    assert "caller_phone_digits" not in state
    assert "caller_phone_confirmation_pending" not in state
    assert state["caller_phone"] == "+919876543210"
    assert first_booking_question(messages) == "ज़रूर। अपॉइंटमेंट किस नाम से बुक करूँ?"
