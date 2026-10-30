"""Phone-only STT fallback selection does not load extra decoders."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def stt_app(monkeypatch):
    monkeypatch.setitem(sys.modules, "sherpa_onnx", SimpleNamespace(OfflineRecognizer=object))
    path = Path(__file__).parents[1] / "local_models" / "indic_stt" / "app.py"
    spec = importlib.util.spec_from_file_location("indic_stt_phone_test_app", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_regional_detector_error_can_rescue_with_previous_hindi_decoder(stt_app):
    assert stt_app._phone_rescue_language(
        "pa", "hi", installed={"hi", "en", "pa"}, resident={"hi", "en", "pa"},
    ) == "hi"


def test_phone_rescue_never_loads_a_nonresident_model(stt_app):
    assert stt_app._phone_rescue_language(
        "pa", "hi", installed={"hi", "en", "pa"}, resident={"pa"},
    ) is None


@pytest.mark.parametrize(
    "primary,fallback,resident,expected",
    [
        ("hi", "hi", {"hi", "en"}, "en"),
        ("en", "hi", {"hi", "en"}, "hi"),
        ("pa", "pa", {"hi", "en", "pa"}, None),
        ("pa", "hi", {"pa"}, None),
    ],
)
def test_rescue_keeps_existing_hi_en_behavior_and_supported_limits(
    stt_app, primary, fallback, resident, expected,
):
    assert stt_app._phone_rescue_language(
        primary, fallback, installed={"hi", "en", "pa"}, resident=resident,
    ) == expected
