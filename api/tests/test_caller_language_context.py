from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from api.services.pipecat.caller_language_context import CallerLanguageContext, standalone_language_request


def recognition(code, text):
    return NS(latest_detected_language=code, latest_detected_text=text)


def test_multilingual_followups_preserve_previous_request_prefix_and_transcript():
    context = CallerLanguageContext()
    history = [{"role": "system", "content": "Support the caller."}]
    previous = None
    for language, utterance in (
        ("ta", "எனது கணக்கில் உதவி வேண்டும்"),
        ("en-IN", "Please explain that in English."),
        ("hi", "अब हिंदी में बताइए"),
    ):
        history.append({"role": "user", "content": utterance})
        original = deepcopy(history)
        request = context.apply(history, recognition(language, utterance))
        assert history == original
        if previous:
            assert request[:len(previous)] == previous
        previous = request
        history.append({"role": "assistant", "content": "A reply in the chosen language."})


@pytest.mark.parametrize("code", [
    "as", "bn", "brx", "doi", "gu", "hi", "kn", "ks", "kok", "mai", "ml",
    "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta", "te", "ur",
])
def test_each_scheduled_indian_language_is_retained_on_next_turn(code):
    context = CallerLanguageContext()
    history = [{"role": "user", "content": "Recognized utterance"}]
    first = context.apply(history, recognition(code, "Recognized utterance"))
    assert first != history
    history.extend([
        {"role": "assistant", "content": "Reply"},
        {"role": "user", "content": "A follow-up"},
    ])
    followup = context.apply(history, recognition("en", "A follow-up"))
    assert followup[0] == first[0]
    assert "Answer in English" in followup[-1]["content"]


def test_tool_and_idle_turns_keep_history_without_copying_stale_language():
    context = CallerLanguageContext()
    history = [{"role": "user", "content": "Help me"}]
    source = recognition("en", "Help me")
    first = context.apply(history, source)
    history.append({"role": "tool", "content": '{"status": "ok"}'})
    tool = context.apply(history, source)
    assert tool[0] == first[0]
    assert tool[-1] == history[-1]
    history.append({"role": "user", "content": "Are you still there?"})
    idle = context.apply(history, source)
    assert idle[0] == first[0]
    assert idle[-1] == history[-1]


def test_empty_detection_cannot_tag_unrelated_messages():
    history = [{"role": "user", "content": "A typed message"}]
    assert CallerLanguageContext().apply(history, recognition("hi", "")) == history


def test_weak_raw_language_guess_does_not_override_confidence_filtered_voice_language():
    source = NS(
        latest_detected_language="ml",
        latest_tts_language=None,
        latest_detected_text="Help me book a room",
    )
    history = [{"role": "user", "content": "Help me book a room"}]

    assert CallerLanguageContext().apply(history, source) == history


def test_explicit_english_request_survives_a_weak_raw_language_guess():
    utterance = "Can you speak in English?"
    source = NS(
        latest_detected_language="ml",
        latest_tts_language=None,
        latest_detected_text=utterance,
    )
    request = CallerLanguageContext()

    tagged = request.apply([{"role": "user", "content": utterance}], source)

    assert "Answer in English" in tagged[0]["content"]
    assert source.reply_language_override == "en"


def test_instances_do_not_share_caller_language_state():
    history = [{"role": "user", "content": "Help"}]
    tagged = CallerLanguageContext().apply(history, recognition("en", "Help"))
    assert tagged != history
    assert CallerLanguageContext().apply(history, None) == history


def test_removed_history_is_forgotten_and_repeated_words_keep_their_own_hint():
    context = CallerLanguageContext()
    history = [{"role": "user", "content": "OK"}]
    first = context.apply(history, recognition("en", "OK"))
    history.extend([
        {"role": "assistant", "content": "Continue?"},
        {"role": "user", "content": "OK"},
    ])
    second = context.apply(history, recognition("hi", "OK"))
    assert second[0] == first[0]
    assert "Answer in Hindi" in second[-1]["content"]
    context.apply([], None)
    assert context.apply(history, None) == history


@pytest.mark.parametrize("utterance", [
    "अः क्या तुम इंग्लिश में बात कर सकते हो",
    "कृपया अंग्रेजी में जवाब दें",
    "Can you speak in English?",
])
def test_explicit_english_switch_overrides_detected_hindi(utterance):
    history = [{"role": "user", "content": utterance}]
    request = CallerLanguageContext().apply(history, recognition("hi", utterance))
    assert "explicitly chose English" in request[0]["content"]
    assert "Reply only in English" in request[0]["content"]
    assert history[0]["content"] == utterance


def test_language_mention_without_switch_keeps_detected_language():
    utterance = "क्या आप इंग्लिश जानते हैं?"
    request = CallerLanguageContext().apply(
        [{"role": "user", "content": utterance}], recognition("hi", utterance)
    )
    assert "Answer in Hindi" in request[0]["content"]


def test_stt_language_without_installed_tts_uses_the_selected_supported_reply_language():
    utterance = "ᱚᱠᱴᱳᱵᱚᱨ"
    source = NS(
        latest_detected_language="sat",
        latest_tts_language="hi",
        latest_detected_text=utterance,
    )
    request = CallerLanguageContext().apply(
        [{"role": "user", "content": utterance}], source
    )
    assert "Answer in Hindi" in request[0]["content"]


def test_explicit_switch_persists_for_a_short_hindi_name_then_resumes_auto_matching():
    context = CallerLanguageContext()
    history = [{"role": "user", "content": "क्या तुम इंग्लिश में बात कर सकते हो"}]
    first = context.apply(history, recognition("hi", history[-1]["content"]))
    history.extend([
        {"role": "assistant", "content": "Yes, I can speak English."},
        {"role": "user", "content": "मेरा नाम आदर्श है"},
    ])
    second = context.apply(history, recognition("hi", history[-1]["content"]))
    assert second[0] == first[0]
    assert "Reply only in English" in second[-1]["content"]
    history.extend([
        {"role": "assistant", "content": "Thank you, Adarsh."},
        {"role": "user", "content": "எனக்கு உதவி வேண்டும்"},
    ])
    third = context.apply(history, recognition("ta", history[-1]["content"]))
    assert "Answer in Tamil" in third[-1]["content"]


@pytest.mark.parametrize("text", [
    "कन यूताार्क इन इंग्लिश",
    "क्या तुम इंग्लिश में प कर सकते हो",
    "Can you talk in English?",
])
def test_standalone_language_switch_from_recognized_call_fragments(text):
    assert standalone_language_request(text) == "English"


@pytest.mark.parametrize("text", [
    "Can you talk in English and book a room?", "Don't speak in English",
    "What does English mean?", "क्या तुम इंग्लिश पढ़ाते हो",
])
def test_other_intents_and_language_negations_are_not_swallowed(text):
    assert standalone_language_request(text) is None


def test_fresh_text_service_recovers_language_choice_from_persisted_history():
    history = [
        {"role": "user", "content": "क्या तुम इंग्लिश में प कर सकते हो"},
        {"role": "assistant", "content": "Yes, we can continue in English."},
        {"role": "user", "content": "मेरा नाम आदर्श है"},
    ]
    request = CallerLanguageContext().apply(history, None)
    assert "Reply only in English" in request[-1]["content"]
    assert history[-1]["content"] == "मेरा नाम आदर्श है"
