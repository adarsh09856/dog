from types import SimpleNamespace

from api.services.pipecat.speaches_stt import (
    _advance_stable_language,
    _is_auto_language,
    _phone_rescue_reply_language,
    _trusted_tts_language,
)
from api.services.pipecat.caller_language_context import CallerLanguageContext
from api.services.pipecat.speaches_tts import SpeachesLiveTTSService


def test_auto_language_sentinel_is_not_treated_as_a_pinned_decoder():
    assert _is_auto_language("auto")
    assert _is_auto_language("multi")
    assert _is_auto_language(None)
    assert not _is_auto_language("hi")


def test_phone_digit_rescue_keeps_the_call_language_instead_of_switching_to_english():
    assert _phone_rescue_reply_language("hi", "auto") == "hi"
    assert _phone_rescue_reply_language("ta", "auto") == "ta"
    assert _phone_rescue_reply_language("en", "auto") == "en"
    assert _phone_rescue_reply_language(None, "hi") == "hi"
    assert _phone_rescue_reply_language(None, "auto") is None


def test_weak_first_language_guess_does_not_force_a_regional_tts_voice():
    assert _trusted_tts_language("mr", 0.3447, None, "detector") is None


def test_missing_detector_confidence_keeps_stable_voice_or_uses_default():
    assert _trusted_tts_language("en", None, "hi", "detector") == "hi"
    assert _trusted_tts_language("mr", None, None, "detector") is None


def test_weak_language_fragment_keeps_the_last_confident_tts_language():
    assert _trusted_tts_language("ta", 0.4583, "hi", "held_previous_low_confidence") == "hi"


def test_one_confident_english_guess_keeps_the_stable_hindi_voice():
    assert _trusted_tts_language("en", 0.5368, "hi", "detector") == "hi"


def test_two_consistent_english_turns_switch_the_stable_reply_and_voice():
    stable, pending, pending_count = _advance_stable_language(
        "hi", "en", 0.5368, "detector", None, 0
    )
    assert stable == "hi"
    assert _trusted_tts_language("en", 0.5368, stable, "detector") == "hi"

    stable, pending, pending_count = _advance_stable_language(
        stable, "en", 0.5368, "detector", pending, pending_count
    )
    assert stable == "en"
    assert _trusted_tts_language("en", 0.5368, stable, "detector") == "en"


def test_verified_english_rescue_can_switch_immediately():
    assert _trusted_tts_language(
        "en", 0.5368, "hi", "competitive_indian_english"
    ) == "en"


def test_recognized_language_without_an_installed_reply_voice_does_not_force_a_fallback():
    assert _trusted_tts_language("sat", 0.978, None, "detector") is None
    assert _trusted_tts_language("sat", 0.978, "en", "detector") == "en"
    assert _trusted_tts_language("sat", 0.978, None, "detector", {"en"}) is None


def test_tts_does_not_fall_back_to_a_weak_raw_stt_guess():
    tts = SpeachesLiveTTSService.__new__(SpeachesLiveTTSService)
    tts._speech_turn_open = False
    tts._speech_language = "auto"
    tts._caller_language_source = SimpleNamespace(
        latest_detected_language="mr",
        latest_tts_language=None,
        _settings=SimpleNamespace(language="auto"),
    )

    assert tts._resolve_speech_language() is None


def test_legacy_stt_sources_keep_their_language_route():
    tts = SpeachesLiveTTSService.__new__(SpeachesLiveTTSService)
    tts._speech_turn_open = False
    tts._speech_language = None
    tts._caller_language_source = SimpleNamespace(
        latest_detected_language="ta",
        _settings=SimpleNamespace(language=None),
    )

    assert tts._resolve_speech_language() == "ta"


def test_explicit_reply_language_overrides_the_previous_stt_language_for_tts():
    source = SimpleNamespace(
        latest_detected_language="hi",
        latest_tts_language="hi",
        latest_detected_text="इंग्लिश में बात कर सकते हो",
    )
    context = CallerLanguageContext()
    context.choose_language("English", source, text="इंग्लिश में बात कर सकते हो")
    context.apply(
        [{"role": "user", "content": "इंग्लिश में बात कर सकते हो"}],
        source,
    )

    tts = SpeachesLiveTTSService.__new__(SpeachesLiveTTSService)
    tts._speech_turn_open = False
    tts._speech_language = "auto"
    tts._settings = SimpleNamespace(model="indic-vits-rasa-13", voice="ENG_IN")
    tts._caller_language_tts_capability_contract = {
        "model": "indic-vits-rasa-13",
        "languages": {"hi", "en"},
        "voices": {"hin_f", "eng_in"},
    }
    tts._caller_language_source = source

    assert source.reply_language_override == "en"
    assert tts._resolve_speech_language() == "en"


def test_new_detected_language_clears_an_old_explicit_tts_override():
    source = SimpleNamespace(
        latest_detected_language="hi",
        latest_tts_language="hi",
        latest_detected_text="हिंदी में बात करो",
    )
    context = CallerLanguageContext()
    context.choose_language("Hindi", source, text="हिंदी में बात करो")
    context.apply([{"role": "user", "content": "हिंदी में बात करो"}], source)
    assert source.reply_language_override == "hi"

    source.latest_detected_language = "en"
    source.latest_tts_language = "en"
    source.latest_detected_text = "Can you help me?"
    context.apply(
        [
            {"role": "user", "content": "हिंदी में बात करो"},
            {"role": "assistant", "content": "ज़रूर, हिंदी में बात करते हैं।"},
            {"role": "user", "content": "Can you help me?"},
        ],
        source,
    )

    assert source.reply_language_override is None
