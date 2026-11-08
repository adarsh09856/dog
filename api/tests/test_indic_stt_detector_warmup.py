import sys
import types
import io

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


def test_local_stt_inventory_exposes_all_scheduled_languages_and_english():
    assert indic_stt.AUTO_DETECT_LANGUAGES == frozenset(indic_stt.LID_LANGUAGE_CODES)
    # Keep all detector labels in their released order for correct logit mapping.
    assert len(indic_stt.LID_LANGUAGE_CODES) == 23
    assert indic_stt.LID_LANGUAGE_CODES[-1] == "ur"
    assert indic_stt.SCHEDULED_INDIAN_LANGUAGES == (
        indic_stt.AUTO_DETECT_LANGUAGES - {"en"}
    )
    assert len(indic_stt.SCHEDULED_INDIAN_LANGUAGES) == 22


def test_auto_detection_uses_an_installed_scheduled_language_decoder():
    assert indic_stt._resolve_decode_language(
        "as", 0.99, None, set(indic_stt.AUTO_DETECT_LANGUAGES),
    ) == ("as", "detector")


def test_detector_preserves_language_argmax_and_uses_its_installed_decoder(monkeypatch):
    logits = [0.0] * len(indic_stt.LID_LANGUAGE_CODES)
    logits[indic_stt.LID_LANGUAGE_CODES.index("ur")] = 8.0
    logits[indic_stt.LID_LANGUAGE_CODES.index("hi")] = 6.0

    class Detector:
        def run(self, *_args):
            return [[logits]]

    monkeypatch.setattr(indic_stt, "_lid_session", Detector())
    monkeypatch.setattr(indic_stt, "_english_lid", None)
    detected, confidence, route = indic_stt._detect_language(
        [0.01] * 16000, 16000
    )

    assert detected == "ur"
    assert confidence > 0.65
    assert route is None
    assert indic_stt._resolve_decode_language(
        detected, confidence, "hi", set(indic_stt.AUTO_DETECT_LANGUAGES),
    ) == ("hi", "urdu_routed_to_hindi")


def test_clear_hindi_prediction_skips_expensive_english_rescue(monkeypatch):
    logits = [0.0] * len(indic_stt.LID_LANGUAGE_CODES)
    logits[indic_stt.LID_LANGUAGE_CODES.index("hi")] = 8.0

    class Detector:
        def run(self, *_args):
            return [[logits]]

    class EnglishDetector:
        calls = 0

        def create_stream(self):
            return self

        def accept_waveform(self, *_args):
            pass

        def compute(self, _stream):
            self.calls += 1
            return "unknown"

    english = EnglishDetector()
    monkeypatch.setattr(indic_stt, "_lid_session", Detector())
    monkeypatch.setattr(indic_stt, "_english_lid", english)

    detected, _confidence, route = indic_stt._detect_language([0.01] * 16_000, 16_000)

    assert detected == "hi"
    assert route is None
    assert english.calls == 0


def test_ambiguous_hindi_english_prediction_still_runs_english_rescue(monkeypatch):
    logits = [0.0] * len(indic_stt.LID_LANGUAGE_CODES)
    logits[indic_stt.LID_LANGUAGE_CODES.index("hi")] = 2.0
    logits[indic_stt.LID_LANGUAGE_CODES.index("en")] = 1.5

    class Detector:
        def run(self, *_args):
            return [[logits]]

    class EnglishDetector:
        def create_stream(self):
            return self

        def accept_waveform(self, *_args):
            pass

        def compute(self, _stream):
            return "en"

    monkeypatch.setattr(indic_stt, "_lid_session", Detector())
    monkeypatch.setattr(indic_stt, "_english_lid", EnglishDetector())

    detected, _confidence, route = indic_stt._detect_language([0.01] * 16_000, 16_000)

    assert detected == "en"
    assert route == "whisper_english_rescue"


def test_auto_detection_does_not_silently_substitute_a_missing_decoder():
    with pytest.raises(indic_stt.HTTPException) as exc_info:
        indic_stt._resolve_decode_language("gu", 0.99, None, {"hi", "en"})
    assert getattr(exc_info.value, "status_code", None) == 422

    assert indic_stt._resolve_decode_language(
        "gu", 0.99, "en", {"hi", "en"},
    ) == ("en", "unsupported_language_held_previous")


def test_urdu_detection_uses_the_installed_hindi_decoder():
    assert indic_stt._resolve_decode_language(
        "ur", 0.99, None, {"hi", "en"},
    ) == ("hi", "urdu_routed_to_hindi")


def test_urdu_detection_uses_hindi_only_when_the_active_voice_enables_it():
    assert indic_stt._resolve_decode_language(
        "ur", 0.99, "en", {"hi", "en"}, allowed_languages={"en"},
    ) == ("en", "unsupported_language_held_previous")

    with pytest.raises(indic_stt.HTTPException) as exc_info:
        indic_stt._resolve_decode_language(
            "ur", 0.99, None, {"hi", "en"}, allowed_languages={"en"},
        )
    assert exc_info.value.status_code == 422


def test_auto_detection_falls_back_only_to_a_voice_enabled_decoder():
    assert indic_stt._resolve_decode_language(
        "gu", 0.99, "hi", {"hi", "en", "gu"}, allowed_languages={"hi", "en"},
    ) == ("hi", "unsupported_language_held_previous")

    with pytest.raises(indic_stt.HTTPException) as exc_info:
        indic_stt._resolve_decode_language(
            "gu", 0.99, None, {"hi", "en", "gu"}, allowed_languages={"hi", "en"},
        )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_auto_transcription_rejects_an_allowlist_with_no_enabled_tts_language(monkeypatch):
    monkeypatch.setattr(indic_stt, "_installed_languages", lambda: ["hi", "en", "gu"])
    with pytest.raises(indic_stt.HTTPException) as exc_info:
        await indic_stt.transcribe(
            file=indic_stt.UploadFile(filename="speech.wav", file=io.BytesIO(b"")),
            model=indic_stt.MODEL_ID,
            language="auto",
            phone_capture=False,
            allowed_languages="ur",
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "no_enabled_tts_languages"
