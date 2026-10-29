from api.services.workflow.contact_context import (
    booking_contact_question,
    booking_phone_date_question,
    caller_state_instruction,
    caller_name_followup_reply,
    caller_phone_fragment_reply,
    remember_recent_caller_statements,
    remember_explicit_caller_name,
)


def test_caller_state_reminder_includes_only_complete_phone_and_valid_name():
    assert caller_state_instruction({"caller_phone_digits": "9538300"}) is None
    reminder = caller_state_instruction({
        "caller_name": "आदर्श",
        "caller_phone": "9538300941",
    })
    assert reminder is not None
    assert '"name": "आदर्श"' in reminder
    assert '"phone": "9538300941"' in reminder
    assert "do not ask for them again" in reminder
    assert "Caller-provided details" in reminder
    assert "Verified caller details" not in reminder


def test_recent_caller_statements_preserve_booking_request_and_date_fragments():
    state = {}
    remember_recent_caller_statements([
        {"role": "user", "content": "मुझे एक रूम बुक करना था"},
        {"role": "assistant", "content": "कृपया तारीख बताइए"},
        {"role": "user", "content": "कल का"},
    ], state)
    # A later context may contain only the last utterance; keep the earlier
    # request and date fragment without promoting assistant questions to facts.
    remember_recent_caller_statements([
        {"role": "user", "content": "ट्वेंटी सेवन अक्टूबर ट्वेंटी ट्वेंटी सिक्स"},
    ], state)

    reminder = caller_state_instruction(state)
    assert reminder is not None
    assert "मुझे एक रूम बुक करना था" in reminder
    assert "कल का" in reminder
    assert "ट्वेंटी सेवन अक्टूबर ट्वेंटी ट्वेंटी सिक्स" in reminder
    assert "कृपया तारीख बताइए" not in reminder
    assert "not confirmations of a booking" in reminder


def test_recent_caller_statements_remain_bounded_and_deduplicated():
    state = {}
    remember_recent_caller_statements([
        {"role": "user", "content": "मुझे कमरा चाहिए"},
    ], state)
    remember_recent_caller_statements([
        {"role": "user", "content": "मुझे कमरा चाहिए"},
        {"role": "user", "content": "कल शाम"},
    ], state)

    assert state["recent_caller_statements"] == ["मुझे कमरा चाहिए", "कल शाम"]


def test_long_booking_intake_retains_the_callers_original_request():
    state = {}
    turns = [
        "मुझे एक रूम बुक करना था",
        "मेरा नाम आदर्श है",
        "मेरा फोन नंबर है नाइन फाइव",
        "थ्री एट थ्री",
        "डबल ज़ीरो नाइन फोर वन",
        "कल का",
        "थिर्टी अक्टूबर",
    ]
    for text in turns:
        # The model can receive a compacted history with only this latest turn.
        remember_recent_caller_statements([{"role": "user", "content": text}], state)

    assert turns[0] in state["recent_caller_statements"]
    assert caller_state_instruction(state) is not None
    assert turns[0] in caller_state_instruction(state)


def test_caller_state_reminder_omits_statements_already_in_model_history():
    state = {"recent_caller_statements": ["मुझे कमरा चाहिए", "कल शाम"]}
    visible = [{"role": "user", "content": "[Reply in Hindi]\nकल शाम"}]

    reminder = caller_state_instruction(state, visible)

    assert reminder is not None
    assert "मुझे कमरा चाहिए" in reminder
    assert "कल शाम" not in reminder
    assert caller_state_instruction(state, [
        {"role": "user", "content": "मुझे कमरा चाहिए"},
        {"role": "user", "content": "कल शाम"},
    ]) is None


def test_hindi_name_answer_advances_to_the_remaining_mobile_number():
    messages = [
        {
            "role": "assistant",
            "content": "नया ऑर्डर बनाने के लिए कृपया अपना नाम और मोबाइल नंबर दें।",
        },
        {"role": "user", "content": "राहुल"},
    ]
    state = {}

    assert caller_name_followup_reply(messages, state) == (
        "धन्यवाद, राहुल जी। अब कृपया मोबाइल नंबर बताइए।"
    )
    assert state["caller_name"] == "राहुल"


def test_booking_name_only_question_advances_without_qwen_when_phone_missing():
    messages = [
        {"role": "user", "content": "मुझे एक अपॉइंटमेंट बुक करना है।"},
        {"role": "assistant", "content": "ज़रूर। अपॉइंटमेंट किस नाम से बुक करूँ?"},
        {"role": "user", "content": "मेरा नाम आदर्श है।"},
    ]
    assert caller_name_followup_reply(messages, {}, booking_available=False) is None
    assert caller_name_followup_reply(
        messages, {}, booking_available=True, known_phone="9538300941"
    ) is None
    state = {}
    assert caller_name_followup_reply(messages, state, booking_available=True) == (
        "धन्यवाद, आदर्श जी। अब कृपया मोबाइल नंबर बताइए।"
    )
    assert state["caller_name"] == "आदर्श"


def test_completed_booking_phone_advances_to_date_without_repeating_digits():
    messages = [
        {"role": "user", "content": "मुझे एक अपॉइंटमेंट बुक करना है।"},
        {"role": "assistant", "content": "अपॉइंटमेंट किस नाम से बुक करूँ?"},
        {"role": "user", "content": "मेरा नाम आदर्श है।"},
        {"role": "assistant", "content": "अब कृपया मोबाइल नंबर बताइए।"},
        {"role": "user", "content": "मेरा नंबर 9999999999 है।"},
    ]
    state = {"caller_name": "आदर्श"}
    confirmation = caller_phone_fragment_reply(messages, state)
    assert confirmation == (
        "मैंने नंबर एक-एक अंक करके सुना: नौ, नौ, नौ, नौ, नौ, नौ, नौ, नौ, नौ, नौ। "
        "क्या यह सही है? हाँ कहें या नंबर दोहराएँ।"
    )
    assert state["caller_phone_confirmation_pending"] == "9999999999"
    messages.extend([
        {"role": "assistant", "content": confirmation},
        {"role": "user", "content": "हाँ"},
    ])
    assert caller_phone_fragment_reply(messages, state) == (
        "धन्यवाद। किस तारीख और समय के लिए बुक करना चाहेंगे?"
    )
    assert state["caller_phone"] == "9999999999"
    reply = booking_phone_date_question(messages, state)
    assert reply == "धन्यवाद। किस तारीख और समय के लिए बुक करना चाहेंगे?"
    assert booking_phone_date_question(messages, state) is None
    assert booking_phone_date_question(messages[2:], {
        "caller_phone": "9999999999", "phone_just_completed": "9999999999"
    }) is None


def test_room_reservation_does_not_enter_appointment_slot_collection():
    messages = [
        {"role": "user", "content": "मुझे एक कमरा बुक करना है।"},
        {"role": "assistant", "content": "कमरे की बुकिंग के लिए आपका नाम क्या है?"},
        {"role": "user", "content": "मेरा नाम आदर्श है।"},
    ]
    state = {}

    # A room request must not be converted into an appointment or calendar write.
    assert caller_name_followup_reply(messages, state, booking_available=True) is None
    assert state.get("awaiting_phone") is not True


def test_english_name_answer_advances_to_the_remaining_phone_number():
    messages = [
        {"role": "assistant", "content": "Please provide your name and phone number."},
        {"role": "user", "content": "My name is Maya Rao."},
    ]

    assert caller_name_followup_reply(messages, {}) == (
        "Thanks, Maya Rao. What's your mobile number?"
    )


def test_name_followup_does_not_claim_short_answers_or_phone_numbers():
    prompt = "Please provide your name and phone number."
    assert caller_name_followup_reply(
        [{"role": "assistant", "content": prompt}, {"role": "user", "content": "Yes"}], {}
    ) is None
    assert caller_name_followup_reply(
        [{"role": "assistant", "content": prompt}, {"role": "user", "content": "+919876543210"}], {}
    ) is None
    assert caller_name_followup_reply(
        [{"role": "assistant", "content": "How can I help?"}, {"role": "user", "content": "Rahul"}], {}
    ) is None


def test_compound_hindi_name_and_incomplete_phone_remember_name():
    state = {}
    messages = [
        {"role": "assistant", "content": "कृपया अपना नाम और संपर्क विवरण दें।"},
        {"role": "user", "content": "मेरा नाम आदर्श है मेरा नंबर है तो है"},
    ]
    remember_explicit_caller_name(messages, state)
    reply = caller_phone_fragment_reply(messages, state)
    assert state["caller_name"] == "आदर्श"
    assert state["awaiting_phone"] is True
    assert "मोबाइल नंबर" in reply
    messages.extend([{"role": "assistant", "content": reply}, {"role": "user", "content": "फोर है"}])
    assert "1 अंक" in caller_phone_fragment_reply(messages, state)
    assert "caller_phone" not in state


def test_unclear_phone_words_are_never_guessed_or_saved():
    state = {"awaiting_phone": True, "caller_name": "आदर्श"}
    messages = [{"role": "user", "content": "अः मेरा फोन नंबर है नीन फाइव तो"}]
    assert caller_phone_fragment_reply(messages, state)
    assert "caller_phone" not in state
    assert state["caller_name"] == "आदर्श"


def test_complete_spoken_digits_are_kept_but_changed_intent_is_not_intercepted():
    state = {"awaiting_phone": True}
    assert caller_phone_fragment_reply([{"role": "user", "content": "I want to cancel the appointment"}], state) is None
    assert state["awaiting_phone"] is True
    assert caller_phone_fragment_reply([{"role": "user", "content": "nine eight seven six five four three two one zero"}], state) is None
    assert state["caller_phone"] == "9876543210"
    assert state["awaiting_phone"] is False


def test_name_followup_honors_explicit_english_reply_choice():
    state = {"reply_language": "English"}
    reply = caller_name_followup_reply([
        {"role": "assistant", "content": "Please provide your name and contact details."},
        {"role": "user", "content": "मेरा नाम आदर्श है"},
    ], state)
    assert reply == "Thanks, आदर्श. What's your mobile number?"
    assert state["caller_name"] == "आदर्श"


def test_explicit_name_is_remembered_and_recalled_without_model():
    state = {}
    first_turn = [{
        "role": "user",
        "content": "मेरा नाम आदर्श है। मुझे एक कमरा बुक करना है।",
    }]
    assert remember_explicit_caller_name(first_turn, state) is None
    assert state["caller_name"] == "आदर्श"
    assert remember_explicit_caller_name(
        [*first_turn, {"role": "user", "content": "What name did I give you?"}], state
    ) == "You told me your name is आदर्श."


def test_explicit_correction_replaces_name_and_phone_is_not_a_name():
    state = {"caller_name": "Adarsh"}
    messages = [
        {"role": "user", "content": "My name is Adarsh."},
        {"role": "assistant", "content": "What is your phone number?"},
        {"role": "user", "content": "Actually, my name is Ravi."},
    ]
    assert remember_explicit_caller_name(messages, state) is None
    assert state["caller_name"] == "Ravi"
    state = {}
    assert remember_explicit_caller_name(
        [{"role": "user", "content": "My name is +919876543210."}], state
    ) is None
    assert "caller_name" not in state


def test_name_is_captured_from_a_compound_request():
    state = {}
    assert remember_explicit_caller_name(
        [{"role": "user", "content": "My name is Adarsh and I need a room."}], state
    ) is None
    assert state["caller_name"] == "Adarsh"


def test_simple_name_answer_is_remembered_when_assistant_asked_for_name():
    state = {}
    messages = [
        {"role": "assistant", "content": "What is your name?"},
        {"role": "user", "content": "आदर्श"},
    ]
    assert remember_explicit_caller_name(messages, state) is None
    assert state["caller_name"] == "आदर्श"


def test_simple_name_capture_does_not_mistake_phone_or_affirmation_for_name():
    for answer in ("+919876543210", "Yes", "नहीं"):
        state = {}
        assert remember_explicit_caller_name([
            {"role": "assistant", "content": "Please tell me your name and number."},
            {"role": "user", "content": answer},
        ], state) is None
        assert "caller_name" not in state


def test_phone_number_can_be_dictated_in_fragments_after_caller_introduces_it():
    state = {}
    first = [{"role": "user", "content": "मेरा नाम आदर्श है, मेरा नंबर है nine eight seven"}]
    assert remember_explicit_caller_name(first, state) is None
    reply = caller_phone_fragment_reply(first, state)
    assert state["caller_name"] == "आदर्श"
    assert state["caller_phone_digits"] == "987"
    assert state["awaiting_phone"] is True
    assert "बाकी अंक" in reply

    second = [*first, {"role": "assistant", "content": reply}, {"role": "user", "content": "six five four hai"}]
    reply = caller_phone_fragment_reply(second, state)
    assert state["caller_phone_digits"] == "987654"
    assert "बाकी अंक" in reply

    third = [*second, {"role": "assistant", "content": reply}, {"role": "user", "content": "three two one zero"}]
    assert caller_phone_fragment_reply(third, state) is None
    assert state["caller_phone"] == "9876543210"
    assert state["awaiting_phone"] is False
    assert "caller_phone_digits" not in state


def test_phone_number_keeps_double_across_stt_turns():
    state = {}
    messages = [{"role": "assistant", "content": "Please tell me your phone number."}]
    for utterance in ("nine five three", "eight three double", "zero", "nine four one"):
        messages.append({"role": "user", "content": utterance})
        reply = caller_phone_fragment_reply(messages, state)
        if reply:
            messages.append({"role": "assistant", "content": reply})
    assert state["caller_phone"] == "9538300941"
    assert state["awaiting_phone"] is False


def test_pending_double_is_discarded_when_caller_changes_intent():
    state = {"awaiting_phone": True, "caller_phone_digits": "95383"}
    assert caller_phone_fragment_reply([{"role": "user", "content": "double"}], state)
    assert caller_phone_fragment_reply([{"role": "user", "content": "cancel the appointment"}], state) is None
    assert caller_phone_fragment_reply([{"role": "user", "content": "zero"}], state)
    assert state["caller_phone_digits"] == "953830"


def test_pending_double_does_not_survive_a_bypassed_fast_reply():
    state = {"awaiting_phone": True, "caller_phone_digits": "95383"}
    history = [{"role": "user", "content": "double"}]
    assert caller_phone_fragment_reply(history, state)
    history.extend([
        {"role": "assistant", "content": "Which digit comes after double?"},
        {"role": "user", "content": "I need help"},
        {"role": "assistant", "content": "What do you need help with?"},
        {"role": "user", "content": "zero"},
    ])
    assert caller_phone_fragment_reply(history, state)
    assert state["caller_phone_digits"] == "953830"


def test_double_does_not_duplicate_a_compound_digit_alias():
    state = {"awaiting_phone": True}
    reply = caller_phone_fragment_reply([{"role": "user", "content": "double फोरन"}], state)
    assert reply is None or "caller_phone" not in state
    assert state.get("caller_phone_digits", "") != "4141"


def test_phone_answer_is_captured_when_previous_agent_turn_asked_for_it():
    state = {}
    messages = [
        {"role": "assistant", "content": "कृपया अपना मोबाइल नंबर बताइए।"},
        {"role": "user", "content": "नीन फाइव फोर"},
    ]
    reply = caller_phone_fragment_reply(messages, state)
    assert state["caller_phone_digits"] == "954"
    assert state["awaiting_phone"] is True
    assert "बाकी अंक" in reply


def test_phone_parser_accepts_plus_as_a_separator_without_losing_country_code():
    state = {"awaiting_phone": True}
    messages = [
        {"role": "assistant", "content": "Tell me your phone number."},
        {"role": "user", "content": "plus nine one nine five three eight three double zero nine four one"},
    ]

    assert caller_phone_fragment_reply(messages, state) is None
    assert state["caller_phone"] == "919538300941"


def test_phone_parser_accepts_spoken_and_between_complete_digits():
    state = {"awaiting_phone": True}
    messages = [
        {"role": "assistant", "content": "Tell me your phone number."},
        {"role": "user", "content": "nine five three eight and three double zero nine four one"},
    ]

    assert caller_phone_fragment_reply(messages, state) is None
    assert state["caller_phone"] == "9538300941"


def test_phone_parser_is_idempotent_for_the_same_user_turn():
    state = {"awaiting_phone": True}
    messages = [
        {"role": "assistant", "content": "Tell me your phone number."},
        {"role": "user", "content": "nine five three eight three"},
    ]

    first_reply = caller_phone_fragment_reply(messages, state)
    first_state = dict(state)
    second_reply = caller_phone_fragment_reply(messages, state)

    assert first_reply is not None
    assert second_reply is None
    assert state == first_state


def test_phone_parser_deduplicates_same_utterance_after_history_compaction():
    state = {"awaiting_phone": True}
    full_history = [
        {"role": "user", "content": "I need an appointment"},
        {"role": "assistant", "content": "Please tell me your phone number."},
        {"role": "user", "content": "nine five three eight three"},
    ]

    first_reply = caller_phone_fragment_reply(full_history, state)
    first_digits = state["caller_phone_digits"]
    compacted_history = [
        {"role": "assistant", "content": "Please tell me your phone number."},
        {"role": "user", "content": "nine five three eight three"},
    ]

    assert first_reply is not None
    assert caller_phone_fragment_reply(compacted_history, state) is None
    assert state["caller_phone_digits"] == first_digits == "95383"


def test_phone_parser_accepts_same_spoken_digits_as_a_new_turn_after_reply():
    state = {"awaiting_phone": True}
    first = [
        {"role": "assistant", "content": "Please tell me your phone number."},
        {"role": "user", "content": "zero"},
    ]
    assert caller_phone_fragment_reply(first, state) is not None
    assert state["caller_phone_digits"] == "0"

    second = [
        *first,
        {"role": "assistant", "content": "I have 1 digit. Please continue."},
        {"role": "user", "content": "zero"},
    ]
    assert caller_phone_fragment_reply(second, state) is not None
    assert state["caller_phone_digits"] == "00"


def test_phone_digits_with_ambiguous_asr_one_request_a_retry():
    state = {}
    messages = [
        {"role": "assistant", "content": "कृपया अपना मोबाइल नंबर बताइए।"},
        {
            "role": "user",
            "content": "Three, eight, three. Double zero. Nine-four on.",
        },
    ]

    reply = caller_phone_fragment_reply(messages, state)

    assert "caller_phone_digits" not in state
    assert state["awaiting_phone"] is True
    assert reply and "फिर से" in reply


def test_unclear_phone_correction_clears_old_number_before_retry():
    state = {
        "awaiting_phone": True,
        "caller_phone": "9876543210",
        "phone_just_completed": "9876543210",
        "approved_phone": "9876543210",
    }
    messages = [
        {"role": "assistant", "content": "Tell me your phone number."},
        {"role": "user", "content": "three eight three double zero nine four on"},
    ]

    reply = caller_phone_fragment_reply(messages, state)

    assert reply and "repeat the full phone number" in reply.lower()
    assert not {"caller_phone", "phone_just_completed", "approved_phone"} & state.keys()


def test_hindi_asr_digit_variants_and_double_zero_are_collected():
    state = {}
    messages = [
        {"role": "assistant", "content": "कृपया अपना फ़ोन नंबर बताइए।"},
        {
            "role": "user",
            "content": "मेरा फोन नंबर है नीन फाइव थी आईट थी डबल जीरो नान फोर zero",
        },
    ]

    assert caller_phone_fragment_reply(messages, state) is None
    assert state["caller_phone"] == "9538300940"


def test_production_hindi_stt_phone_phrase_is_accepted_without_retry():
    state = {}
    messages = [
        {"role": "assistant", "content": "कृपया अपना फ़ोन नंबर बताइए।"},
        {
            "role": "user",
            "content": "मेरा फ़ोन नंबर है नाइन फ़ाइव थ्री ऐट थ्री डबल ज़ीरो नाइन फ़ोर वन",
        },
    ]

    assert caller_phone_fragment_reply(messages, state) is None
    assert state["caller_phone"] == "9538300941"
    assert state["awaiting_phone"] is False


def test_hindi_stt_joined_four_one_digit_token_is_accepted_in_phone_context():
    state = {}
    messages = [
        {"role": "assistant", "content": "कृपया अपना मोबाइल नंबर बताइए।"},
        {
            "role": "user",
            "content": "मेरा फोन नंबर है नीन फाइव थ्री आइट थ्री डबल जीरो नाइन फोरन",
        },
    ]

    assert caller_phone_fragment_reply(messages, state) is None
    assert state["caller_phone"] == "9538300941"
    assert state["awaiting_phone"] is False


def test_phone_number_split_between_tamil_and_gujarati_script_is_collected():
    state = {}
    first = [
        {"role": "assistant", "content": "कृपया अपना मोबाइल नंबर बताइए।"},
        {"role": "user", "content": "નાઇન ફાઇવ த்ரீ ஏஐட் த்ரீ டபுள் ஜீரோ"},
    ]

    reply = caller_phone_fragment_reply(first, state)
    assert state["caller_phone_digits"] == "9538300"
    assert state["awaiting_phone"] is True
    assert reply and "3 अंक" in reply

    second = [*first, {"role": "assistant", "content": reply}, {
        "role": "user", "content": "નાઇન ફોર વન",
    }]
    assert caller_phone_fragment_reply(second, state) is None
    assert state["caller_phone"] == "9538300941"
    assert state["awaiting_phone"] is False


def test_regional_spoken_digits_are_captured_as_ascii():
    examples = (
        "নয় আট সাত ছয় পাঁচ চার তিন দুই এক শূন্য",
        "ஒன்பது எட்டு ஏழு ஆறு ஐந்து நான்கு மூன்று இரண்டு ஒன்று பூஜ்யம்",
        "తొమ్మిది ఎనిమిది ఏడు ఆరు ఐదు నాలుగు మూడు రెండు ఒకటి సున్నా",
        "ಒಂಬತ್ತು ಎಂಟು ಏಳು ಆರು ಐದು ನಾಲ್ಕು ಮೂರು ಎರಡು ಒಂದು ಸೊನ್ನೆ",
        "ഒൻപത് എട്ട് ഏഴ് ആറ് അഞ്ച് നാല് മൂന്ന് രണ്ട് ഒന്ന് പൂജ്യം",
        "ਨੌਂ ਅੱਠ ਸੱਤ ਛੇ ਪੰਜ ਚਾਰ ਤਿੰਨ ਦੋ ਇੱਕ ਸਿਫ਼ਰ",
        "नऊ आठ सात सहा पाच चार तीन दोन एक शून्य",
    )
    for text in examples:
        state = {}
        messages = [
            {"role": "assistant", "content": "Please tell me your phone number."},
            {"role": "user", "content": text},
        ]
        assert caller_phone_fragment_reply(messages, state) is None
        assert state["caller_phone"] == "9876543210"


def test_non_ascii_numerals_are_normalized_to_ascii_including_double():
    state = {}
    messages = [
        {"role": "assistant", "content": "Please tell me your phone number."},
        {"role": "user", "content": "৯৮৭৬৫৪৩২১০"},
    ]
    assert caller_phone_fragment_reply(messages, state) is None
    assert state["caller_phone"] == "9876543210"
    state = {"awaiting_phone": True, "caller_phone_digits": "98765432"}
    assert caller_phone_fragment_reply([{"role": "user", "content": "double ০"}], state) is None
    assert state["caller_phone"] == "9876543200"


def test_full_phone_retry_replaces_unclear_attempt_instead_of_appending():
    state = {}
    first = [
        {"role": "assistant", "content": "कृपया अपना फ़ोन नंबर बताइए।"},
        {
            "role": "user",
            "content": "मेरा फोन नंबर है नीन फाइव अस्पष्ट थी आईट थी डबल जीरो नान फोर zero",
        },
    ]
    reply = caller_phone_fragment_reply(first, state)
    assert reply and "पूरा फ़ोन नंबर फिर से" in reply
    assert state["replace_phone_digits_on_next_turn"] is True

    repeated = [
        *first,
        {"role": "assistant", "content": reply},
        {
            "role": "user",
            "content": "नाइन फाइव थी आइट थी डबल जीरो नान फोर zero",
        },
    ]
    assert caller_phone_fragment_reply(repeated, state) is None
    assert state["caller_phone"] == "9538300940"
    assert "caller_phone_digits" not in state


def test_repeated_incomplete_phone_number_replaces_digits_instead_of_overflowing():
    state = {"awaiting_phone": True}
    utterance = "नाइन फाइव थ्री आइट थी डबल जीरो नाइन फोर"
    first = [
        {"role": "assistant", "content": "कृपया अपना फ़ोन नंबर बताइए।"},
        {"role": "user", "content": utterance},
    ]

    reply = caller_phone_fragment_reply(first, state)
    assert state["caller_phone_digits"] == "953830094"
    assert "1 अंक" in reply

    repeated = [
        *first,
        {"role": "assistant", "content": reply},
        {"role": "user", "content": utterance},
    ]
    retry_reply = caller_phone_fragment_reply(repeated, state)

    assert state["caller_phone_digits"] == "953830094"
    assert state["awaiting_phone"] is True
    assert state.get("caller_phone") is None
    assert "too many digits" not in (retry_reply or "").casefold()
    assert "1 अंक" in retry_reply


def test_caller_provided_phone_is_reused_without_asking_for_known_phone_again():
    messages = [{"role": "user", "content": "I want to book an appointment."}]
    contact = {"customer_name": "Adarsh", "customer_phone": "+919876543210"}
    state = {"caller_name": "Adarsh", "caller_phone": "9876543210"}
    assert booking_contact_question(messages, contact, state) is None
