from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from api.services.pipecat.caller_language_context import CallerLanguageContext


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
