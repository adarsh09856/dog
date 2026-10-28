from api.services.workflow.booking_response_guard import guard_booking_reply


def test_hallucinated_booking_success_claim_gets_constructive_next_step():
    reply = guard_booking_reply(
        "Your appointment is confirmed.", [], language="en"
    )

    assert reply == (
        "I can help finish the booking. Let’s check the details and save it through the calendar."
    )
    assert "not confirmed" not in reply.casefold()
    assert "not verify" not in reply.casefold()


def test_failed_booking_action_explains_next_step_without_claiming_success():
    events = [{
        "type": "tool_call_result",
        "payload": {"function_name": "book_appointment", "result": {"booked": False}},
    }]

    assert guard_booking_reply("Your appointment is booked.", events, language="en") == (
        "That time didn’t save. Let’s choose another time and try again."
    )


def test_hindi_booking_guard_is_constructive():
    assert guard_booking_reply(
        "आपकी बुकिंग पक्की हो गई।", [], language="hi-IN"
    ) == "मैं बुकिंग पूरी करने में मदद करूँगी। चलिए विवरण जाँचकर इसे कैलेंडर में सेव करते हैं।"
