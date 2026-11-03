import pytest

from api.services.workflow.contact_context import (
    booking_contact_question,
    booking_time_confirmation_question,
)


_CONTACT = {"customer_name": "Adarsh", "customer_phone": "+919876543210"}


@pytest.mark.parametrize(
    ("utterance", "assistant_prompt", "language", "expected_slot"),
    [
        ("8 AM", "What time works for you?", "English", "08:00"),
        ("eight am", "What time works for you?", "English", "08:00"),
        ("सुबह आठ बजे", "कल का समय क्या है?", "Hindi", "08:00"),
        ("आठ AM", "कल का समय क्या है?", "Hindi", "08:00"),
        ("आठ बजे AM", "कल का समय क्या है?", "Hindi", "08:00"),
        ("आठ पी एम", "कल का समय क्या है?", "Hindi", "20:00"),
    ],
)
def test_common_english_and_hindi_time_forms_are_parsed(
    utterance, assistant_prompt, language, expected_slot
):
    state = {
        "reply_language": language,
        "caller_name": "Adarsh",
        "caller_phone": "+919876543210",
        "approved_phone": "+919876543210",
        "booking_time_question_date": "2099-10-27",
    }
    messages = [
        {"role": "user", "content": "I want to book an appointment"},
        {"role": "assistant", "content": assistant_prompt},
        {"role": "user", "content": utterance},
    ]

    reply = booking_contact_question(messages, _CONTACT, state)

    assert state["booking_confirmation_slot"] == f"2099-10-27T{expected_slot}"
    if language == "Hindi":
        assert "अक्टूबर" in reply
    else:
        assert "October" in reply


def test_staged_date_survives_shortened_history_and_time_question_rewording():
    state = {
        "reply_language": "English",
        "booking_time_question_date": "2099-10-27",
    }
    messages = [
        {"role": "assistant", "content": "Please tell me the time once more."},
        {"role": "user", "content": "8 AM"},
    ]

    reply = booking_time_confirmation_question(messages, state)

    assert reply and "8:00 AM" in reply
    assert state["booking_time_question_date"] == "2099-10-27"
    assert state["booking_confirmation_slot"] == "2099-10-27T08:00"


@pytest.mark.parametrize(
    ("assistant_prompt", "utterance", "language"),
    [
        ("What time works for you?", "8 AM", "English"),
        ("Your date is clear. What would you prefer?", "8am", "English"),
        ("What time works for you?", "eight a m", "English"),
        ("कितने बजे चाहिए?", "eight am", "English"),
        ("कल का दिन स्पष्ट है, लेकिन कितने समय पर आपका संपर्क रख सकता हूँ?", "eight am", "Hindi"),
        ("कितने बजे चाहिए?", "8 ए एम", "Hindi"),
        ("कितने बजे चाहिए?", "8 AM", "Hindi"),
        ("कितने बजे चाहिए?", "सुबह आठ बजे", "Hindi"),
    ],
)
def test_short_time_answer_survives_trimmed_conversation_history(
    assistant_prompt, utterance, language
):
    state = {
        "reply_language": language,
        "caller_name": "Adarsh",
        "caller_phone": "+919876543210",
        "approved_phone": "+919876543210",
        "booking_time_question_date": "2099-10-27",
    }
    # The booking intent and date are earlier than the context window; only
    # the active date slot and the last assistant question remain.
    messages = [
        {"role": "assistant", "content": assistant_prompt},
        {"role": "user", "content": utterance},
    ]

    reply = booking_contact_question(messages, _CONTACT, state)

    assert state["booking_confirmation_slot"] == "2099-10-27T08:00"
    if language == "Hindi":
        assert "सुबह 8:00 बजे" in reply
    else:
        assert "8:00 AM" in reply


@pytest.mark.parametrize("utterance", ["13 AM", "thirteen am"])
def test_invalid_clock_hour_is_not_staged(utterance):
    state = {
        "caller_name": "Adarsh",
        "caller_phone": "+919876543210",
        "approved_phone": "+919876543210",
        "booking_time_question_date": "2099-10-27",
    }
    messages = [
        {"role": "user", "content": "I want to book an appointment"},
        {"role": "assistant", "content": "What time works for you?"},
        {"role": "user", "content": utterance},
    ]

    booking_contact_question(messages, _CONTACT, state)

    assert "booking_confirmation_slot" not in state


@pytest.mark.parametrize(
    ("period", "expected_slot"),
    [
        ("AM", "2099-10-27T08:00"),
        ("P M", "2099-10-27T20:00"),
        ("पी एम", "2099-10-27T20:00"),
        ("सुबह", "2099-10-27T08:00"),
    ],
)
def test_time_hour_and_period_can_arrive_in_separate_speech_turns(period, expected_slot):
    state = {
        "reply_language": "English",
        "caller_name": "Adarsh",
        "caller_phone": "+919876543210",
        "approved_phone": "+919876543210",
        "booking_time_question_date": "2099-10-27",
    }
    messages = [
        {"role": "assistant", "content": "What time do you prefer?"},
        {"role": "user", "content": "eight"},
    ]

    first_reply = booking_contact_question(messages, _CONTACT, state)
    assert first_reply == "You said 8. Is that AM or PM?"
    assert state["booking_pending_time_hour"] == 8
    assert "booking_confirmation_slot" not in state

    messages.extend([
        {"role": "assistant", "content": first_reply},
        {"role": "user", "content": period},
    ])
    second_reply = booking_contact_question(messages, _CONTACT, state)

    assert state["booking_confirmation_slot"] == expected_slot
    expected_display = "8:00 AM" if "T08:00" in expected_slot else "8:00 PM"
    assert f"at {expected_display}" in second_reply
    assert "booking_pending_time_hour" not in state


def test_hindi_hour_and_english_period_can_arrive_in_separate_turns():
    state = {
        "reply_language": "Hindi",
        "caller_name": "Adarsh",
        "caller_phone": "+919876543210",
        "approved_phone": "+919876543210",
        "booking_time_question_date": "2099-10-27",
    }
    messages = [
        {"role": "assistant", "content": "कल का समय क्या है?"},
        {"role": "user", "content": "आठ"},
    ]

    first_reply = booking_contact_question(messages, _CONTACT, state)
    assert first_reply == "आपने 8 बजे कहा—सुबह या शाम?"
    messages.extend([
        {"role": "assistant", "content": first_reply},
        {"role": "user", "content": "पी एम"},
    ])
    second_reply = booking_contact_question(messages, _CONTACT, state)

    assert state["booking_confirmation_slot"] == "2099-10-27T20:00"
    assert "शाम 8:00 बजे" in second_reply
