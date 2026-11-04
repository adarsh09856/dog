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


def test_local_stt_inventory_exposes_all_22_scheduled_languages_and_english():
    assert indic_stt.AUTO_DETECT_LANGUAGES == frozenset(indic_stt.LID_LANGUAGE_CODES)
    assert indic_stt.SCHEDULED_INDIAN_LANGUAGES == (
        indic_stt.AUTO_DETECT_LANGUAGES - {"en"}
    )
    assert len(indic_stt.SCHEDULED_INDIAN_LANGUAGES) == 22


def test_auto_detection_uses_an_installed_scheduled_language_decoder():
    assert indic_stt._resolve_decode_language(
        "ur", 0.99, None, set(indic_stt.AUTO_DETECT_LANGUAGES),
    ) == ("ur", "detector")


def test_auto_detection_does_not_silently_substitute_a_missing_decoder():
    with pytest.raises(indic_stt.HTTPException) as exc_info:
        indic_stt._resolve_decode_language("gu", 0.99, "en", {"hi", "en"})
    assert getattr(exc_info.value, "status_code", None) == 422

    assert indic_stt._resolve_decode_language(
        "gu", 0.10, "en", {"hi", "en"},
    ) == ("en", "unsupported_language_held_previous")
