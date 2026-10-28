import sys
import types

import pytest

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


def test_excluded_auto_detection_falls_back_to_supported_language_without_urdu_transcript():
    assert indic_stt._resolve_decode_language(
        "ur", 0.99, None, {"hi", "en"},
    ) == ("hi", "excluded_language_to_hindi")
    assert indic_stt._resolve_decode_language(
        "gu", 0.99, "en", {"hi", "en"},
    ) == ("en", "excluded_language_to_previous_supported")
