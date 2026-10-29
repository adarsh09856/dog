from api.services.workflow.contact_context import remember_explicit_caller_name


def test_prompted_correction_survives_later_recall_and_history_replay():
    state = {}
    messages = [
        {"role": "user", "content": "My name is Maya Rao."},
        {"role": "assistant", "content": "Please confirm your name."},
        {"role": "user", "content": "Anita Singh"},
    ]
    assert remember_explicit_caller_name(messages, state) is None
    assert state["caller_name"] == "Anita Singh"
    messages += [
        {"role": "assistant", "content": "How can I help?"},
        {"role": "user", "content": "What name did I give you?"},
    ]
    for _ in range(2):
        assert remember_explicit_caller_name(messages, state) == "You told me your name is Anita Singh."
        assert state["caller_name"] == "Anita Singh"


def test_hindi_prompted_correction_survives_later_turn():
    messages = [
        {"role": "user", "content": "मेरा नाम माया है।"},
        {"role": "assistant", "content": "आपका नाम क्या है?"},
        {"role": "user", "content": "अनीता सिंह"},
        {"role": "assistant", "content": "कैसे मदद करूँ?"},
        {"role": "user", "content": "मेरा नाम क्या है?"},
    ]
    state = {}
    assert remember_explicit_caller_name(messages, state) == "आपने अपना नाम अनीता सिंह बताया था।"


def test_explicit_hindi_name_without_copula_does_not_store_intro_words():
    state = {}
    remember_explicit_caller_name([
        {"role": "assistant", "content": "आपका नाम क्या है?"},
        {"role": "user", "content": "मेरा नाम माया"},
    ], state)
    assert state["caller_name"] == "माया"


def test_later_explicit_correction_wins_over_prompted_answer():
    state = {}
    messages = [
        {"role": "assistant", "content": "Your name, please?"},
        {"role": "user", "content": "Maya Rao"},
        {"role": "assistant", "content": "How can I help?"},
        {"role": "user", "content": "Actually, my name is Anita Singh."},
        {"role": "assistant", "content": "Thank you."},
        {"role": "user", "content": "What name did I give you?"},
    ]
    assert remember_explicit_caller_name(messages, state) == "You told me your name is Anita Singh."


def test_missing_old_history_does_not_clear_call_scoped_name():
    state = {"caller_name": "Anita Singh"}
    assert remember_explicit_caller_name([
        {"role": "assistant", "content": "How can I help?"},
        {"role": "user", "content": "What name did I give you?"},
    ], state) == "You told me your name is Anita Singh."


def test_phone_fragments_and_language_switches_do_not_replace_name():
    for reply in ("nine five three", "9538300941", "speak in English", "हिंदी में बोलो", "switch to Tamil"):
        state = {"caller_name": "Anita Singh"}
        remember_explicit_caller_name([
            {"role": "assistant", "content": "Please confirm your name."},
            {"role": "user", "content": reply},
        ], state)
        assert state["caller_name"] == "Anita Singh"


def test_name_state_is_call_scoped_and_same_name_replay_is_idempotent():
    first_state = {}
    other_state = {"caller_name": "Maya Rao"}
    messages = [{"role": "user", "content": "My name is Anita Singh."}]
    for _ in range(2):
        remember_explicit_caller_name(messages, first_state)
        assert first_state["caller_name"] == "Anita Singh"
        assert other_state["caller_name"] == "Maya Rao"


def test_consecutive_speech_fragments_do_not_replace_answered_name():
    messages = [
        {"role": "assistant", "content": "What is your name?"},
        {"role": "user", "content": "Anita Singh"},
        {"role": "user", "content": "I need help"},
        {"role": "assistant", "content": "How can I help?"},
        {"role": "user", "content": "What name did I give you?"},
    ]
    state = {}
    assert remember_explicit_caller_name(messages, state) == "You told me your name is Anita Singh."
    assert state["caller_name"] == "Anita Singh"


def test_repeated_name_in_date_question_does_not_capture_date_as_name():
    for answer in ("tomorrow", "later please", "कल"):
        state = {"caller_name": "Anita Singh"}
        remember_explicit_caller_name([
            {"role": "assistant", "content": "Your name is Anita Singh. What date would you prefer?"},
            {"role": "user", "content": answer},
        ], state)
        assert state["caller_name"] == "Anita Singh"

    for prompt in ("आपका नाम अनीता है। तारीख क्या है?", "आपका नाम अनीता है, तारीख क्या है?"):
        state = {"caller_name": "अनीता"}
        remember_explicit_caller_name([
            {"role": "assistant", "content": prompt},
            {"role": "user", "content": "कल"},
        ], state)
        assert state["caller_name"] == "अनीता"


def test_hindi_name_and_phone_prompt_accepts_name_answer():
    state = {}
    remember_explicit_caller_name([
        {"role": "assistant", "content": "कृपया अपना नाम और फोन नंबर बताएं।"},
        {"role": "user", "content": "अनीता सिंह"},
    ], state)
    assert state["caller_name"] == "अनीता सिंह"
