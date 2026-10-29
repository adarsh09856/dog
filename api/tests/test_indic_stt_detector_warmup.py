import asyncio
import io
import sys
import types
from collections import OrderedDict
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

# Production installs sherpa-onnx in the isolated STT image. Unit tests only
# exercise warm-up orchestration and do not need the native inference package.
sys.modules.setdefault("sherpa_onnx", types.ModuleType("sherpa_onnx"))
from api.local_models.indic_stt import app as indic_stt


def test_detector_startup_warmup_exercises_primary_and_english_paths(monkeypatch):
    primary_calls = []

    def detect(audio, sample_rate):
        primary_calls.append((audio.copy(), sample_rate))
        # An English prediction skips the rescue inside _detect_language, so
        # the startup warmup must invoke that classifier itself.
        return "en", 0.9, None

    class EnglishDetector:
        def __init__(self):
            self.accepted = []
            self.computed = 0

        def create_stream(self):
            return self

        def accept_waveform(self, sample_rate, audio):
            self.accepted.append((sample_rate, audio.copy()))

        def compute(self, _stream):
            self.computed += 1
            return "unknown"

    english = EnglishDetector()
    monkeypatch.setattr(indic_stt, "_lid_session", object())
    monkeypatch.setattr(indic_stt, "_english_lid", english)
    monkeypatch.setattr(indic_stt, "_detect_language", detect)

    indic_stt._warm_language_identifiers()

    assert len(primary_calls) == 1
    primary_audio, primary_rate = primary_calls[0]
    assert primary_rate == 16_000
    assert primary_audio.shape == (4 * 16_000,)
    assert primary_audio.dtype.name == "float32"
    assert len(english.accepted) == 1
    assert english.accepted[0][0] == 16_000
    assert english.computed == 1


def test_detector_startup_warmup_fails_if_primary_lid_is_unavailable(monkeypatch):
    monkeypatch.setattr(indic_stt, "_lid_session", None)

    with pytest.raises(RuntimeError, match="not available"):
        indic_stt._warm_language_identifiers()


def test_local_stt_inventory_keeps_requested_languages_and_excludes_urdu_and_unwanted_languages():
    assert indic_stt.AUTO_DETECT_LANGUAGES == frozenset({
        "as", "bn", "brx", "doi", "en", "hi", "kn", "mai", "ml", "mr",
        "ne", "pa", "sa", "ta", "te",
    })
    assert not indic_stt.AUTO_DETECT_LANGUAGES.intersection({
        "gu", "ks", "kok", "mni", "or", "sat", "sd", "ur",
    })


def test_phone_english_rescue_uses_candidate_only_when_it_recovers_more_digits():
    assert indic_stt._phone_digit_count("नंबर नौ, पाँच, थ्री, double zero") == 5
    assert indic_stt._phone_digit_count("nine five 383 double zero 941") == 10
    assert indic_stt._phone_digit_count("nine-five 383 double-zero 941") == 10
    assert indic_stt._phone_rescue_is_better("pre-ed pre-double-zero", "nine five 383 double zero 941")
    assert not indic_stt._phone_rescue_is_better("nine five 383 double zero 941", "nine five 383 double zero 941")
    assert not indic_stt._phone_rescue_is_better("नौ पाँच तीन", "ordinary English words")
    assert indic_stt._phone_digit_count("999999999999999999999999999999") == 30
    assert indic_stt._phone_rescue_is_better(
        "999999999999999999999999999999", "nine five three eight three double zero nine four one"
    )
    assert indic_stt._phone_rescue_is_better(
        "999999999999999999999999999999", "the phone is"
    )


def test_phone_rescue_digit_score_counts_existing_regional_spellings():
    assert indic_stt._phone_digit_count("ஒன்று இரண்டு மூன்று") == 3
    assert indic_stt._phone_digit_count("ಒಂದು ಎರಡು ಮೂರು") == 3
    assert indic_stt._phone_digit_count("ਪੰਜ ਛੇ ਸੱਤ") == 3
    assert not indic_stt._phone_rescue_is_better("ஒன்று இரண்டு மூன்று", "nine five")


def test_phone_rescue_does_not_replace_phonetic_hindi_digits_with_incomplete_english():
    # The Hindi recognizer may spell English digits phonetically in Devanagari.
    # Treat those as explicit primary digits so an incomplete Moonshine result
    # cannot replace a complete caller number merely because of script choice.
    hindi_text = "नीन फाइव थी आइट थी डबल जीरो नाइन फोर वन"
    assert indic_stt._phone_digit_count(hindi_text) == 10
    assert not indic_stt._phone_rescue_is_better(
        hindi_text, "nine five three eight double zero"
    )


def test_phone_rescue_digit_score_counts_phonetic_gujarati_and_tamil_forms():
    assert indic_stt._phone_digit_count("નાઇન ફાઇવ થ્રી એઇટ ફોર વન") == 6
    assert indic_stt._phone_digit_count("நைன் ஃபைவ் த்ரீ ஏய்ட் ஃபோர்") == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("hindi_text", "expected_text", "expected_route", "expected_decodes"),
    [
        (
            "pre-ed pre-double-zero",
            "nine five 383 double zero 941",
            "phone_english_rescue",
            ["hi", "en"],
        ),
        (
            "nine five 383 double zero 941",
            "nine five 383 double zero 941",
            "detector",
            ["hi", "en"],
        ),
    ],
)
async def test_phone_capture_uses_resident_english_decode_only_when_hindi_number_is_incomplete(
    monkeypatch, hindi_text, expected_text, expected_route, expected_decodes
):
    decode_calls = []

    class Stream:
        def __init__(self, text):
            self.result = SimpleNamespace(text=text)

        def accept_waveform(self, _sample_rate, _waveform):
            pass

    class Recognizer:
        def __init__(self, language, text):
            self.language = language
            self.text = text

        def create_stream(self):
            return Stream(self.text)

        def decode_stream(self, _stream):
            decode_calls.append(self.language)

    sample = np.full(4800, 0.05, dtype=np.float32)
    audio = io.BytesIO()
    sf.write(audio, sample, 16000, format="WAV")

    class Upload:
        async def read(self, _limit):
            return audio.getvalue()

    monkeypatch.setattr(indic_stt, "_installed_languages", lambda: ["en", "hi"])
    monkeypatch.setattr(indic_stt, "_lid_session", object())
    monkeypatch.setattr(indic_stt, "_inference_lock", asyncio.Lock())
    monkeypatch.setattr(indic_stt, "_loaded", OrderedDict([("en", object())]))
    monkeypatch.setattr(indic_stt, "_detect_language", lambda *_: ("hi", 0.95, None))
    monkeypatch.setattr(indic_stt, "_load", lambda lang: Recognizer(
        lang,
        hindi_text if lang == "hi" else "nine five 383 double zero 941",
    ))

    result = await indic_stt.transcribe(
        file=Upload(), model=indic_stt.MODEL_ID, language="auto",
        fallback_language="", phone_capture=True,
    )

    assert result["text"] == expected_text
    assert result["language"] == "hi"  # Keep reply/voice language stable.
    assert result["language_route"] == expected_route
    assert decode_calls == expected_decodes


@pytest.mark.asyncio
async def test_phone_capture_rescues_english_routed_hallucinated_digits_with_hindi_decode(monkeypatch):
    decode_calls = []

    class Stream:
        def __init__(self, text):
            self.result = SimpleNamespace(text=text)
        def accept_waveform(self, _sample_rate, _waveform):
            pass

    class Recognizer:
        def __init__(self, language):
            self.language = language
        def create_stream(self):
            return Stream("")
        def decode_stream(self, stream):
            decode_calls.append(self.language)
            stream.result.text = (
                "999999999999999999999999999999" if self.language == "en"
                else "नाइन फाइव थ्री एट थ्री डबल जीरो नाइन फोर वन"
            )

    audio = io.BytesIO()
    sf.write(audio, np.full(4800, 0.05, dtype=np.float32), 16000, format="WAV")
    class Upload:
        async def read(self, _limit):
            return audio.getvalue()

    monkeypatch.setattr(indic_stt, "_installed_languages", lambda: ["en", "hi"])
    monkeypatch.setattr(indic_stt, "_lid_session", object())
    monkeypatch.setattr(indic_stt, "_inference_lock", asyncio.Lock())
    monkeypatch.setattr(indic_stt, "_loaded", OrderedDict([("en", object()), ("hi", object())]))
    monkeypatch.setattr(indic_stt, "_detect_language", lambda *_: ("en", 0.996, None))
    monkeypatch.setattr(indic_stt, "_load", lambda lang: Recognizer(lang))

    result = await indic_stt.transcribe(
        file=Upload(), model=indic_stt.MODEL_ID, language="auto",
        fallback_language="hi", phone_capture=True,
    )

    assert result["text"] == "नाइन फाइव थ्री एट थ्री डबल जीरो नाइन फोर वन"
    assert result["language"] == "en"  # Keep detected language for downstream reply routing.
    assert result["language_route"] == "phone_hi_rescue"
    assert decode_calls == ["en", "hi"]


def test_excluded_auto_detection_falls_back_to_supported_language_without_urdu_transcript():
    assert indic_stt._resolve_decode_language(
        "ur", 0.99, None, {"hi", "en"},
    ) == ("hi", "excluded_language_to_hindi")
    assert indic_stt._resolve_decode_language(
        "gu", 0.99, "en", {"hi", "en"},
    ) == ("en", "excluded_language_to_previous_supported")
