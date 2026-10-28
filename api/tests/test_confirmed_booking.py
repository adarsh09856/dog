from api.services.workflow.confirmed_booking import confirmed_booking_arguments, first_booking_question


def test_full_explicit_confirmation_parses_exact_details():
    actual = confirmed_booking_arguments(
        "I confirm and authorize saving a consultation appointment for Test Booking, "
        "phone +15555550123, on 15 October 2026 at 10:00 AM IST (UTC+05:30). "
        "Save this booking now."
    )
    assert actual == {
        "customer_name": "Test Booking",
        "customer_phone": "+15555550123",
        "start_time": "2026-10-15T10:00:00+05:30",
        "confirmed_by_caller": True,
    }


def test_missing_or_negated_confirmation_never_parses():
    assert confirmed_booking_arguments(
        "Do not save it. I confirm the appointment for Test Booking, phone "
        "+15555550123, on 15 October 2026 at 10:00 AM UTC+05:30."
    ) is None


def test_explicit_hindi_confirmation_preserves_name_and_zoned_date():
    result = confirmed_booking_arguments(
        'मैं राहुल अपॉइंटमेंट की पुष्टि करता हूँ। मेरा फोन +15555550123 है। '
        '16 अक्टूबर 2026 को दोपहर 12:00 बजे UTC+05:30 पर बुक करें।')
    assert result == {'customer_name': 'राहुल', 'customer_phone': '+15555550123',
                      'start_time': '2026-10-16T12:00:00+05:30', 'confirmed_by_caller': True}


def test_hindi_missing_timezone_or_negative_request_cannot_book():
    text = 'मैं राहुल अपॉइंटमेंट की पुष्टि करता हूँ। फोन +15555550123 है। 16 अक्टूबर 2026 सुबह 10:00 बजे बुक करें।'
    assert confirmed_booking_arguments(text) is None
    assert confirmed_booking_arguments(text + ' UTC+05:30 बुक नहीं करें।') is None
    assert confirmed_booking_arguments(
        "Please save my appointment for Test Booking, phone +15555550123, "
        "on 15 October 2026 at 10:00 AM UTC+05:30."
    ) is None


def test_full_hinglish_confirmation_with_ist_parses_exact_details():
    assert confirmed_booking_arguments(
        "Haan, confirm hai. Mera naam Local Test, phone +919000000002. "
        "Date 16 October 2026, 4 PM IST, timezone Asia/Kolkata. Book kar dijiye."
    ) == {
        "customer_name": "Local Test",
        "customer_phone": "+919000000002",
        "start_time": "2026-10-16T16:00:00+05:30",
        "confirmed_by_caller": True,
    }


def test_hinglish_confirmation_without_explicit_zone_cannot_book():
    assert confirmed_booking_arguments(
        "Haan, confirm hai. Mera naam Local Test, phone +919000000002. "
        "Date 16 October 2026, 4 PM. Book kar dijiye."
    ) is None


def test_first_booking_question_is_short_and_matches_the_callers_language():
    assert first_booking_question([
        {"role": "user", "content": "I want to book an appointment tomorrow at 10 AM."}
    ]) == "Sure. What name should I use for the appointment?"
    assert first_booking_question([
        {"role": "user", "content": "Mujhe appointment book karna hai"}
    ]) == "Bilkul. Appointment kis naam se book karun?"
    assert first_booking_question([
        {"role": "user", "content": "मुझे अपॉइंटमेंट बुक करनी है"}
    ]) == "ज़रूर। अपॉइंटमेंट किस नाम से बुक करूँ?"


def test_first_booking_question_does_not_repeat_name_request_or_trigger_for_information():
    assert first_booking_question([
        {"role": "user", "content": "My name is Rahul, book an appointment."}
    ]) is None
    assert first_booking_question([
        {"role": "user", "content": "What are your appointment hours?"}
    ]) is None


def test_first_booking_question_handles_later_turn_without_forgetting_name():
    assert first_booking_question([
        {"role": "user", "content": "What services do you offer?"},
        {"role": "assistant", "content": "How can I help?"},
        {"role": "user", "content": "I want to book an appointment tomorrow afternoon."},
    ]) == "Sure. What name should I use for the appointment?"
    assert first_booking_question([
        {"role": "user", "content": "My name is Adarsh."},
        {"role": "assistant", "content": "How can I help?"},
        {"role": "user", "content": "I want to book an appointment."},
    ]) is None
