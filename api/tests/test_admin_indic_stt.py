"""Admin diagnostics for the installed local IndicConformer engine."""

import asyncio
import base64
import io
import wave
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.routes.admin import settings


def wav_base64() -> str:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(16000)
        clip.writeframes(b"\0\0" * 1600)
    return base64.b64encode(buffer.getvalue()).decode()


def run(coro):
    return asyncio.run(coro)


def test_indic_stt_test_rejects_unsupported_language_before_service_call(monkeypatch):
    monkeypatch.setattr(settings.kodewaves_db_client, "get_setting", AsyncMock(return_value={}))
    inventory = AsyncMock()
    monkeypatch.setattr(settings, "_get_indic_stt_inventory", inventory)

    with pytest.raises(HTTPException) as error:
        run(settings.test_indic_stt({"language": "en", "audio_base64": wav_base64()}))

    assert error.value.status_code == 400
    inventory.assert_not_awaited()


def test_indic_stt_test_requires_language_to_be_installed(monkeypatch):
    monkeypatch.setattr(settings.kodewaves_db_client, "get_setting", AsyncMock(return_value={}))
    monkeypatch.setattr(settings, "_get_indic_stt_inventory", AsyncMock(return_value={
        "model": {"id": "indicconformer-ctc-int8"}, "languages": ["hi"],
        "endpoint": "http://indic-stt:8000/v1",
    }))
    transcribe = AsyncMock()
    monkeypatch.setattr("api.services.catalog.speech_diagnostics.transcribe_test_audio", transcribe)

    with pytest.raises(HTTPException) as error:
        run(settings.test_indic_stt({"language": "ta", "audio_base64": wav_base64()}))

    assert error.value.status_code == 400
    transcribe.assert_not_awaited()


def test_indic_stt_test_runs_selected_installed_language(monkeypatch):
    monkeypatch.setattr(settings.kodewaves_db_client, "get_setting", AsyncMock(return_value={}))
    monkeypatch.setattr(settings, "_get_indic_stt_inventory", AsyncMock(return_value={
        "model": {"id": "indicconformer-ctc-int8"}, "languages": ["hi", "ta"],
        "endpoint": "http://indic-stt:8000/v1",
    }))
    expected = {"success": True, "model": "indicconformer-ctc-int8", "language": "hi", "transcript": "नमस्ते", "latency_ms": 85}
    transcribe = AsyncMock(return_value=expected)
    monkeypatch.setattr("api.services.catalog.speech_diagnostics.transcribe_test_audio", transcribe)

    result = run(settings.test_indic_stt({"language": "hi-IN", "audio_base64": wav_base64()}))

    assert result == expected
    args = transcribe.await_args.args
    assert args[0] == "http://indic-stt:8000/v1"
    assert args[2:] == ("indicconformer-ctc-int8", "hi")


def test_indic_stt_test_rejects_non_wav_audio(monkeypatch):
    monkeypatch.setattr(settings.kodewaves_db_client, "get_setting", AsyncMock(return_value={}))
    with pytest.raises(HTTPException) as error:
        run(settings.test_indic_stt({"language": "hi", "audio_base64": base64.b64encode(b"not wav").decode()}))
    assert error.value.status_code == 400
