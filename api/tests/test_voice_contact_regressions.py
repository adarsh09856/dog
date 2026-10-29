from datetime import date, datetime, timedelta, timezone

from api.services.workflow import contact_context as contacts


def test_booking_intake_does_not_drop_a_second_request():
    for text in (
        "I want to book an appointment and tell me your opening hours",
        "I want to book a room and tell me your opening hours",
        "मुझे एक अपॉइंटमेंट बुक करना है और आपका समय क्या है",
        "Mujhe appointment book karna hai aur price bataiye",
    ):
        state = {}
        assert contacts.booking_contact_question(
            [{"role": "user", "content": text}], {}, state
        ) is None
        assert not state


def test_ambiguous_asr_one_variants_require_readback_confirmation_before_saving_phone():
    for unclear in ("on", "run", "won", "wan"):
        state = {"awaiting_phone": True}
        messages = [
            {"role": "assistant", "content": "Please tell me your phone number."},
            {"role": "user", "content": f"nine five three eight three double zero nine four {unclear}"},
        ]
        reply = contacts.caller_phone_fragment_reply(messages, state)
        assert reply and "ending in 0941" in reply
        assert "caller_phone" not in state
        assert state["caller_phone_confirmation_pending"] == "9538300941"
        messages.extend([
            {"role": "assistant", "content": reply},
            {"role": "user", "content": "yes"},
        ])
        assert "Thanks" in contacts.caller_phone_fragment_reply(messages, state)
        assert state["caller_phone"] == "9538300941"
        assert "caller_phone_confirmation_pending" not in state


def test_ambiguous_asr_phone_candidate_is_discarded_when_caller_says_no():
    state = {"awaiting_phone": True}
    messages = [
        {"role": "assistant", "content": "Please tell me your phone number."},
        {"role": "user", "content": "nine five three eight three double zero nine four run"},
    ]
    prompt = contacts.caller_phone_fragment_reply(messages, state)
    messages.extend([
        {"role": "assistant", "content": prompt},
        {"role": "user", "content": "no"},
    ])
    retry = contacts.caller_phone_fragment_reply(messages, state)
    assert retry and "repeat the full phone number" in retry.lower()
    assert "caller_phone" not in state
    assert "caller_phone_confirmation_pending" not in state


def test_confirmed_ambiguous_phone_advances_booking_without_reasking_number():
    state = {"awaiting_phone": True, "reply_language": "English"}
    messages = [
        {"role": "user", "content": "I want to book an appointment"},
        {"role": "assistant", "content": "Please tell me your phone number."},
        {"role": "user", "content": "nine five three eight three double zero nine four run"},
    ]
    confirmation = contacts.caller_phone_fragment_reply(messages, state)
    messages.extend([
        {"role": "assistant", "content": confirmation},
        {"role": "user", "content": "yes"},
    ])

    next_question = contacts.caller_phone_fragment_reply(messages, state)

    assert next_question == "Thanks. What date and time would you prefer for the booking?"
    assert state["caller_phone"] == "9538300941"
    assert "caller_phone_confirmation_pending" not in state


def test_phone_prompt_does_not_consume_other_intent_containing_on():
    state = {"awaiting_phone": True}
    messages = [{"role": "user", "content": "Can I book on October nine?"}]
    assert contacts.caller_phone_fragment_reply(messages, state) is None
    assert "caller_phone" not in state


def test_booking_phone_reads_back_mixed_spoken_and_numeric_groups_digit_by_digit():
    state = {"awaiting_phone": True, "reply_language": "English"}
    messages = [
        {"role": "user", "content": "I want to book an appointment"},
        {"role": "assistant", "content": "Please tell me your phone number."},
        {"role": "user", "content": "nine five 383 double zero 941"},
    ]

    reply = contacts.caller_phone_fragment_reply(messages, state)

    assert reply == (
        "I heard: nine, five, three, eight, three, zero, zero, nine, four, one. "
        "Is that correct? Say yes, or repeat the number."
    )
    assert state["caller_phone_confirmation_pending"] == "9538300941"
    assert "caller_phone" not in state
    assert state["awaiting_phone"] is True

    messages.extend([
        {"role": "assistant", "content": reply},
        {"role": "user", "content": "yes"},
    ])
    next_question = contacts.caller_phone_fragment_reply(messages, state)

    assert next_question == "Thanks. What date and time would you prefer for the booking?"
    assert state["caller_phone"] == "9538300941"
    assert state["awaiting_phone"] is False


def test_booking_phone_readback_uses_hindi_digit_names_and_preserves_each_zero():
    state = {"awaiting_phone": True}
    messages = [
        {"role": "user", "content": "मुझे अपॉइंटमेंट बुक करना है"},
        {"role": "assistant", "content": "कृपया अपना मोबाइल नंबर बताइए।"},
        {"role": "user", "content": "nine five 383 double zero 941"},
    ]

    reply = contacts.caller_phone_fragment_reply(messages, state)

    assert reply == (
        "मैंने नंबर एक-एक अंक करके सुना: नौ, पाँच, तीन, आठ, तीन, शून्य, शून्य, "
        "नौ, चार, एक। क्या यह सही है? हाँ कहें या नंबर दोहराएँ।"
    )
    assert state["caller_phone_confirmation_pending"] == "9538300941"
    assert "caller_phone" not in state


def test_unclear_spoken_phone_digits_trigger_repeat_without_guessing():
    state = {"awaiting_phone": True}
    messages = [
        {"role": "assistant", "content": "अब कृपया मोबाइल नंबर बताइए।"},
        {"role": "user", "content": "Nine-five pre-ed pre-double-zero-nine-four-one."},
    ]
    reply = contacts.caller_phone_fragment_reply(messages, state)
    assert reply and "repeat" in reply.lower() or reply and "फिर से" in reply
    assert "caller_phone" not in state
    messages.extend([
        {"role": "assistant", "content": reply},
        {"role": "user", "content": "Nine-five, three-eight-three, double-zero, nine-four-one."},
    ])
    assert contacts.caller_phone_fragment_reply(messages, state) is None
    assert state["caller_phone"] == "9538300941"
    changed_intent = [
        {"role": "assistant", "content": "Please provide your phone number."},
        {"role": "user", "content": "Cancel order nine five three eight three"},
    ]
    assert contacts.caller_phone_fragment_reply(changed_intent, {"awaiting_phone": True}) is None


def test_unintelligible_phone_words_return_retry_instead_of_falling_through_to_llm():
    state = {"awaiting_phone": True}
    messages = [
        {"role": "assistant", "content": "कृपया अपना मोबाइल नंबर बताइए।"},
        {"role": "user", "content": "Nine-five pre-ed pre-double-zero-nine-four-one."},
    ]

    reply = contacts.caller_phone_fragment_reply(messages, state)

    assert reply is not None
    assert "repeat" in reply.lower() or "फिर से" in reply
    assert "caller_phone" not in state


def test_confirmed_booking_uses_known_name_and_explicitly_approved_number():
    messages = [
        {"role": "user", "content": "I want to book an appointment"},
        {"role": "assistant", "content": "I have 10 January 2099 at 10:00 AM IST. Should I book the appointment for that time?"},
        {"role": "user", "content": "Yes"},
    ]
    state = {"approved_phone": "+91 98765 43210", "booking_time_question_date": "2099-01-10", "booking_confirmation_slot": "2099-01-10T10:00"}
    contact = {"customer_name": "Adarsh", "customer_phone": "+91 98765 43210"}
    result = contacts.confirmed_staged_booking_arguments(messages, state, contact)
    assert result and result["customer_name"] == "Adarsh"
    assert result["customer_phone"] == "+91 98765 43210"
    assert result["confirmed_by_caller"] is True
    assert contacts.confirmed_staged_booking_arguments(messages, {k: v for k, v in state.items() if k != "approved_phone"}, contact) is None
    assert contacts.confirmed_staged_booking_arguments([*messages[:-1], {"role": "user", "content": "No"}], state, contact) is None


def test_booking_date_uses_india_today_and_reads_back_corrections(monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 27, 17, 0, tzinfo=tz or timezone(timedelta(hours=5, minutes=30)))

    monkeypatch.setattr(contacts, "datetime", FrozenDatetime)
    state = {"caller_name": "आदर्श", "caller_phone": "9876543210", "reply_language": "Hindi"}
    history = [{"role": "user", "content": "मुझे अपॉइंटमेंट बुक करना था"},
               {"role": "assistant", "content": "किस तारीख और समय के लिए?"},
               {"role": "user", "content": "कल का"}]
    assert "28 अक्टूबर 2026" in contacts.booking_date_time_question(history, state)
    history.extend([{"role": "assistant", "content": "किस समय चाहिए?"},
                    {"role": "user", "content": "हः थिर्टी अक्टूबर"}])
    assert "30 अक्टूबर 2026" in contacts.booking_date_time_question(history, state)
    assert state["booking_time_question_date"] == "2026-10-30"
    assert contacts._explicit_caller_booking_date(["30 October"], reference_date=date(2026, 11, 1)) is None
    assert contacts._explicit_caller_booking_date(["first March 2099"]) == "2099-03-01"
    assert contacts._explicit_caller_booking_date(["27th October 2099"]) == "2099-10-27"


def test_unclear_time_after_relative_booking_date_asks_for_time(monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 28, 10, 0, tzinfo=tz or timezone(timedelta(hours=5, minutes=30)))

    monkeypatch.setattr(contacts, "datetime", FrozenDatetime)
    state = {
        "caller_name": "Adarsh",
        "caller_phone": "9876543210",
        "reply_language": "English",
    }
    history = [
        {"role": "user", "content": "I want to book an appointment"},
        {"role": "assistant", "content": "What date and time would you prefer?"},
        {"role": "user", "content": "Tomorrow's telepm."},
    ]

    reply = contacts.booking_contact_question(history, {}, state)

    assert reply == "Okay, 29 October 2026. What time works for you?"
    assert "booking_confirmation_slot" not in state


def test_repeated_relative_date_does_not_fall_through_and_invent_a_time(monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 29, 10, 0, tzinfo=tz or timezone(timedelta(hours=5, minutes=30)))

    monkeypatch.setattr(contacts, "datetime", FrozenDatetime)
    state = {
        "caller_name": "Adarsh",
        "caller_phone": "9538300941",
        "reply_language": "English",
    }
    history = [
        {"role": "user", "content": "I want to book an appointment"},
        {"role": "assistant", "content": "What date and time would you prefer for the booking?"},
        {"role": "user", "content": "Tomorrow's telepm."},
    ]

    reply = contacts.booking_contact_question(history, {}, state)

    assert reply == "Okay, 30 October 2026. What time works for you?"
    assert "booking_confirmation_slot" not in state

    history.extend([
        {"role": "assistant", "content": reply},
        {"role": "user", "content": "Tomorrow's telepm."},
    ])
    repeated_reply = contacts.booking_contact_question(history, {}, state)

    assert repeated_reply == "Okay, 30 October 2026. What time works for you?"
    assert "booking_confirmation_slot" not in state


def test_booking_combined_tomorrow_and_time_is_confirmed_without_reasking(monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 28, 10, 0, tzinfo=tz or timezone(timedelta(hours=5, minutes=30)))

    monkeypatch.setattr(contacts, "datetime", FrozenDatetime)
    state = {
        "caller_name": "आदर्श",
        "caller_phone": "9876543210",
        "reply_language": "Hindi",
    }
    history = [
        {"role": "user", "content": "मुझे अपॉइंटमेंट बुक करना है"},
        {"role": "assistant", "content": "किस तारीख और समय के लिए बुक करना चाहेंगे?"},
        {"role": "user", "content": "कल शाम 5 बजे"},
    ]

    reply = contacts.booking_contact_question(
        history, {"customer_name": "आदर्श"}, state
    )

    assert reply == (
        "29 अक्टूबर 2026 को शाम 5:00 बजे भारतीय समय। "
        "क्या इस समय के लिए बुकिंग कर दूँ?"
    )
    assert state["booking_time_question_date"] == "2026-10-29"
    assert state["booking_confirmation_slot"] == "2026-10-29T17:00"


def test_combined_explicit_date_and_time_replaces_previous_date(monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 28, 10, 0, tzinfo=tz or timezone(timedelta(hours=5, minutes=30)))

    monkeypatch.setattr(contacts, "datetime", FrozenDatetime)
    state = {
        "caller_name": "Adarsh",
        "caller_phone": "9876543210",
        "reply_language": "English",
        "booking_time_question_date": "2026-10-29",
    }
    history = [
        {"role": "user", "content": "I want to book an appointment"},
        {"role": "assistant", "content": "What date and time works for you?"},
        {"role": "user", "content": "30 October 2026 at 5 PM"},
    ]

    reply = contacts.booking_contact_question(
        history, {"customer_name": "Adarsh"}, state
    )

    assert reply == (
        "I have 30 October 2026 at 5:00 PM IST. "
        "Should I book the appointment for that time?"
    )
    assert state["booking_time_question_date"] == "2026-10-30"
    assert state["booking_confirmation_slot"] == "2026-10-30T17:00"


def test_spoken_hindi_hour_is_confirmed_after_tomorrow_time_prompt(monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 28, 10, 0, tzinfo=tz or timezone(timedelta(hours=5, minutes=30)))

    monkeypatch.setattr(contacts, "datetime", FrozenDatetime)
    state = {
        "caller_name": "आदर्श",
        "caller_phone": "9876543210",
        "reply_language": "Hindi",
    }
    history = [
        {"role": "user", "content": "मुझे अपॉइंटमेंट बुक करना है"},
        {"role": "assistant", "content": "कल का समय क्या है?"},
        {"role": "user", "content": "कल शाम पाँच बजे"},
    ]

    reply = contacts.booking_contact_question(
        history, {"customer_name": "आदर्श"}, state
    )

    assert reply == (
        "29 अक्टूबर 2026 को शाम 5:00 बजे भारतीय समय। "
        "क्या इस समय के लिए बुकिंग कर दूँ?"
    )
    assert state["booking_confirmation_slot"] == "2026-10-29T17:00"


def test_spoken_english_hour_uses_saved_date_and_confirms_slot():
    state = {
        "caller_name": "Adarsh",
        "caller_phone": "9876543210",
        "reply_language": "English",
        "booking_time_question_date": "2026-10-29",
    }
    history = [
        {"role": "user", "content": "I want to book an appointment"},
        {"role": "assistant", "content": "What time works for you?"},
        {"role": "user", "content": "five PM"},
    ]

    reply = contacts.booking_contact_question(
        history, {"customer_name": "Adarsh"}, state
    )

    assert reply == (
        "I have 29 October 2026 at 5:00 PM IST. "
        "Should I book the appointment for that time?"
    )
    assert state["booking_confirmation_slot"] == "2026-10-29T17:00"
