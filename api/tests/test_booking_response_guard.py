from api.services.workflow.booking_response_guard import (
    UNVERIFIED_BOOKING_REPLY,
    guard_booking_reply,
)


def test_unverified_booking_claim_is_suppressed():
    assert guard_booking_reply("I have saved the appointment. The appointment ID is [insert appointment ID here].", []) == UNVERIFIED_BOOKING_REPLY


def test_successful_booking_claim_is_kept():
    events = [{"type": "tool_call_result", "payload": {"function_name": "book_appointment", "result": {"booked": True, "appointment_id": 123}}}]
    assert guard_booking_reply("Your appointment is booked with ID 123.", events) == "Your appointment is booked. Appointment ID: 123. Time: see the appointments calendar."


def test_failed_booking_claim_is_suppressed():
    events = [{"type": "tool_call_result", "payload": {"function_name": "book_appointment", "result": {"booked": False}}}]
    assert guard_booking_reply("Your appointment is booked.", events) == UNVERIFIED_BOOKING_REPLY


def test_question_is_kept():
    assert guard_booking_reply("Would you like to book an appointment?", []) == "Would you like to book an appointment?"


def test_hindi_confirmation_question_is_kept_but_false_success_is_blocked():
    assert guard_booking_reply('क्या मैं आपकी अपॉइंटमेंट बुक कर दूँ?', [], language='hi') == 'क्या मैं आपकी अपॉइंटमेंट बुक कर दूँ?'
    assert guard_booking_reply('आपकी अपॉइंटमेंट बुक हो गई है।', [], language='hi') == 'कैलेंडर में आपकी बुकिंग की पुष्टि नहीं हो सकी। कृपया विवरण जाँचकर फिर कोशिश करें।'


def test_hindi_success_uses_actual_calendar_id():
    events = [{'type': 'tool_call_result', 'payload': {'function_name': 'book_appointment', 'result': {'booked': True, 'appointment_id': 'actual-123', 'start_time': '2026-10-16T10:00:00+05:30'}}}]
    reply = guard_booking_reply('आपकी अपॉइंटमेंट बुक हो गई है।', events, language='hi')
    assert reply.startswith('आपकी अपॉइंटमेंट बुक हो गई है।')
    assert 'actual-123' in reply
    assert 'actual-123' in guard_booking_reply(None, events, language='hi')
    assert 'actual-123' in guard_booking_reply('Please fill the required fields.', events, language='hi')
