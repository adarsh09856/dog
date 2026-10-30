"""Supported-auto language inventory and stable-route hysteresis coverage."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.pipecat.speaches_stt import (
    BoundedSpeachesSTTService,
    LOCAL_REPLY_TTS_LANGUAGES,
    _advance_stable_language,
    _resolve_auto_language,
    _trusted_tts_language,
)


@pytest.fixture
def local_stt_app(monkeypatch):
    monkeypatch.setitem(sys.modules, "sherpa_onnx", SimpleNamespace(OfflineRecognizer=object))
    path = Path(__file__).parents[1] / "local_models" / "indic_stt" / "app.py"
    spec = importlib.util.spec_from_file_location("auto_language_inventory_test_app", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_advertised_auto_languages_match_reply_route_and_exclusions(local_stt_app):
    supported = set(local_stt_app.AUTO_DETECT_LANGUAGES)
    excluded = set(local_stt_app.LID_LANGUAGE_CODES) - supported

    assert supported == LOCAL_REPLY_TTS_LANGUAGES
    assert len(supported - {"en"}) == 14
    assert excluded == {"gu", "ks", "kok", "mni", "or", "sat", "sd", "ur"}


@pytest.mark.parametrize("language", sorted(LOCAL_REPLY_TTS_LANGUAGES))
def test_each_advertised_language_is_accepted_at_calibrated_confidence(language):
    selected, route = _resolve_auto_language(language, 0.9, "hi")
    assert selected == language
    assert route == "detector"


@pytest.mark.parametrize("language", ["gu", "ks", "kok", "mni", "or", "sat", "sd"])
def test_user_excluded_languages_retain_supported_context(language):
    assert _resolve_auto_language(language, 0.95, "mr") == (
        "mr", "excluded_language_to_previous_supported",
    )
    assert _resolve_auto_language(language, 0.95, None) == (
        "hi", "excluded_language_to_hindi",
    )


def test_urdu_remains_excluded_and_routes_to_hindi():
    assert _resolve_auto_language("ur", 0.99, "en") == ("hi", "urdu_routed_to_hindi")


def test_missing_detector_confidence_cannot_switch_or_become_tts_language():
    assert _resolve_auto_language("pa", None, "hi") == (
        "hi", "missing_detector_confidence",
    )
    assert _resolve_auto_language("pa", None, None) == (
        None, "missing_detector_confidence",
    )
    assert _trusted_tts_language("pa", None, "hi", "detector") == "hi"
    assert _trusted_tts_language("pa", None, None, "detector") is None


@pytest.mark.parametrize("language", sorted(LOCAL_REPLY_TTS_LANGUAGES - {"hi"}))
def test_one_confident_challenger_turn_does_not_replace_stable_fallback(language):
    stable, pending, count = _advance_stable_language(
        "hi", language, 0.95, "detector", None, 0,
    )
    assert (stable, pending, count) == ("hi", language, 1)

    stable, pending, count = _advance_stable_language(
        stable, language, 0.95, "detector", pending, count,
    )
    assert (stable, pending, count) == (language, None, 0)


def test_low_confidence_or_interrupted_challenger_cannot_make_a_route_sticky():
    stable, pending, count = _advance_stable_language(
        "hi", "mr", 0.9, "detector", None, 0,
    )
    assert (stable, pending, count) == ("hi", "mr", 1)

    stable, pending, count = _advance_stable_language(
        stable, "hi", 0.9, "detector", pending, count,
    )
    assert (stable, pending, count) == ("hi", None, 0)

    stable, pending, count = _advance_stable_language(
        stable, "mr", 0.9, "detector", pending, count,
    )
    assert (stable, pending, count) == ("hi", "mr", 1)
    stable, pending, count = _advance_stable_language(
        stable, "hi", 0.3, "held_previous_low_confidence", pending, count,
    )
    assert (stable, pending, count) == ("hi", None, 0)


@pytest.mark.asyncio
async def test_current_turn_can_route_candidate_while_stable_fallback_waits_for_confirmation():
    class TranscriptionResult(SimpleNamespace):
        def model_copy(self, *, update):
            return TranscriptionResult(**{**vars(self), **update})

    service = object.__new__(BoundedSpeachesSTTService)
    service._settings = SimpleNamespace(
        model="indicconformer-ctc-int8", language="auto", prompt=None, temperature=0.0,
    )
    service._stable_detected_language = "hi"
    service._pending_detected_language = None
    service._pending_detected_language_count = 0
    service.latest_tts_language = None
    service.latest_detected_language = None
    service.latest_decoder_language = None
    service.latest_detected_text = None
    service._latest_language_confidence = None
    service.phone_capture_pending = None
    first = TranscriptionResult(
        text="मला मदत पाहिजे",
        language="mr",
        model_extra={
            "detected_language": "mr", "language_confidence": 0.91,
            "language_route": "detector",
        },
    )
    second = TranscriptionResult(
        text="मला अजून मदत हवी",
        language="mr",
        model_extra={
            "detected_language": "mr", "language_confidence": 0.93,
            "language_route": "detector",
        },
    )
    create = AsyncMock(side_effect=[first, second])
    service._client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
    )

    first_result = await service._transcribe(b"not-a-wav")
    assert first_result.language == "mr"
    assert service.latest_tts_language == "mr"
    assert service._stable_detected_language == "hi"

    second_result = await service._transcribe(b"not-a-wav")
    assert second_result.language == "mr"
    assert service.latest_tts_language == "mr"
    assert service._stable_detected_language == "mr"
