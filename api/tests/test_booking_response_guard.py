from api.services.workflow.booking_response_guard import (
    UNVERIFIED_BOOKING_REPLY,
    guard_booking_reply,
)


def test_unverified_booking_claim_gets_constructive_next_step():
    reply = guard_booking_reply(
        "Your appointment is confirmed.", [], language="en"
    )
    assert reply == UNVERIFIED_BOOKING_REPLY
    assert "not confirmed" not in reply.casefold()
    assert "not verify" not in reply.casefold()


def test_successful_booking_claim_uses_the_real_calendar_result():
    events = [{"type": "tool_call_result", "payload": {"function_name": "book_appointment", "result": {"booked": True, "appointment_id": 123}}}]
    assert guard_booking_reply("Your appointment is booked with ID 123.", events) == "Your appointment is booked. Appointment ID: 123. Time: see the appointments calendar."


def test_failed_booking_action_explains_next_step_without_claiming_success():
    events = [{"type": "tool_call_result", "payload": {"function_name": "book_appointment", "result": {"booked": False}}}]
    reply = guard_booking_reply("Your appointment is booked.", events, language="en")
    assert reply == "That time didn’t save. Let’s choose another time and try again."
    assert "booked" not in reply.casefold()


def test_booking_question_is_kept():
    assert guard_booking_reply("Would you like to book an appointment?", []) == "Would you like to book an appointment?"


def test_hindi_confirmation_question_is_kept_and_false_success_is_constructive():
    assert guard_booking_reply('क्या मैं आपकी अपॉइंटमेंट बुक कर दूँ?', [], language='hi') == 'क्या मैं आपकी अपॉइंटमेंट बुक कर दूँ?'
    assert guard_booking_reply('आपकी अपॉइंटमेंट बुक हो गई है।', [], language='hi') == 'मैं बुकिंग पूरी करने में मदद करूँगी। चलिए विवरण जाँचकर इसे कैलेंडर में सेव करते हैं।'


def test_hindi_booking_guard_uses_constructive_next_step():
    assert guard_booking_reply('आपकी बुकिंग पक्की हो गई।', [], language='hi-IN') == 'मैं बुकिंग पूरी करने में मदद करूँगी। चलिए विवरण जाँचकर इसे कैलेंडर में सेव करते हैं।'


def test_hindi_success_uses_actual_calendar_id():
    events = [{'type': 'tool_call_result', 'payload': {'function_name': 'book_appointment', 'result': {'booked': True, 'appointment_id': 'actual-123', 'start_time': '2026-10-16T10:00:00+05:30'}}}]
    reply = guard_booking_reply('आपकी अपॉइंटमेंट बुक हो गई है।', events, language='hi')
    assert reply.startswith('आपकी अपॉइंटमेंट बुक हो गई है।')
    assert 'actual-123' in reply
    assert 'actual-123' in guard_booking_reply(None, events, language='hi')
    assert 'actual-123' in guard_booking_reply('Please fill the required fields.', events, language='hi')
