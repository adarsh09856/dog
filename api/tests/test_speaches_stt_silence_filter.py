import pytest
import io
import wave
from array import array
from openai.types.audio import Transcription

from api.services.pipecat.speaches_stt import BoundedSpeachesSTTService
from api.services.pipecat.speaches_stt import (
    _normalize_quiet_pcm16_wav,
    _resolve_script_language_conflict,
)
from pipecat.services.speaches.stt import SpeachesSTTService
from types import SimpleNamespace
from unittest.mock import AsyncMock


@pytest.mark.parametrize(
    "detected,text,previous,expected,route",
    [
        ("pa", "नमस्ते, मुझे मदद चाहिए", None, "hi", "script_conflict_pa_to_devanagari"),
        ("pa", "नमस्कार", "mr", "mr", "script_conflict_pa_to_devanagari"),
        ("pa", "I need help with my booking", "hi", "en", "script_conflict_pa_to_latin"),
        ("pa", "Mujhe help चाहिए", "hi", "hi", "script_conflict_pa_to_devanagari"),
        ("hi", "ਸਤ ਸ੍ਰੀ ਅਕਾਲ", None, "pa", "script_conflict_to_gurmukhi"),
        ("pa", "ਸਤ ਸ੍ਰੀ ਅਕਾਲ", None, "pa", "script_consistent"),
        ("en", "hello, नमस्ते", None, "en", "script_consistent"),
        ("hi", "please help me book an appointment", "hi", "en", "script_conflict_hi_to_latin"),
    ],
)
def test_auto_language_script_conflict_keeps_supported_reply_language(
    detected, text, previous, expected, route,
):
    assert _resolve_script_language_conflict(detected, text, previous) == (expected, route)


def _wav(samples):
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(array("h", samples).tobytes())
    return out.getvalue()


def test_local_stt_normalizes_quiet_speech_without_clipping():
    source = _wav([0, 800, -800, 1200, -1200] * 100)
    result = _normalize_quiet_pcm16_wav(source)
    assert result != source
    with wave.open(io.BytesIO(result), "rb") as reader:
        samples = array("h", reader.readframes(reader.getnframes()))
    assert max(abs(sample) for sample in samples) > 1200
    assert max(abs(sample) for sample in samples) <= 29490
    assert _normalize_quiet_pcm16_wav(_wav([0] * 500)) == _wav([0] * 500)


@pytest.mark.parametrize("text", ["।।।।", "...", "!!!", " — "])
@pytest.mark.asyncio
async def test_local_whisper_punctuation_only_hallucination_is_ignored(
    monkeypatch, text
):
    response = Transcription(text=text)

    async def fake_transcribe(self, audio):
        return response

    monkeypatch.setattr(SpeachesSTTService, "_transcribe", fake_transcribe)
    service = object.__new__(BoundedSpeachesSTTService)

    result = await service._transcribe(b"wav")

    assert result.text == ""


@pytest.mark.parametrize("text", ["नमस्ते", "hello there", "हां yes", "123"])
@pytest.mark.asyncio
async def test_local_whisper_keeps_real_words_and_digits(monkeypatch, text):
    response = Transcription(text=text)

    async def fake_transcribe(self, audio):
        return response

    monkeypatch.setattr(SpeachesSTTService, "_transcribe", fake_transcribe)
    service = object.__new__(BoundedSpeachesSTTService)

    result = await service._transcribe(b"wav")

    assert result.text == text


@pytest.mark.asyncio
async def test_local_whisper_preserves_detected_language_without_changing_transcript():
    service = object.__new__(BoundedSpeachesSTTService)
    service._settings = SimpleNamespace(
        model="Systran/faster-whisper-small", language=None,
        prompt=None, temperature=0.0,
    )
    transcription = SimpleNamespace(text="I need help", language="en")
    create = AsyncMock(return_value=transcription)
    service._client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
    )

    result = await service._transcribe(b"wav")

    assert result.text == "I need help"
    assert service.latest_detected_language == "en"
    assert service.latest_detected_text == "I need help"
    assert create.await_args.kwargs["response_format"] == "verbose_json"


@pytest.mark.asyncio
async def test_indic_auto_route_does_not_make_punjabi_sticky_for_devanagari_hindi():
    service = object.__new__(BoundedSpeachesSTTService)
    service._settings = SimpleNamespace(
        model="indicconformer-ctc-int8", language="auto", prompt=None, temperature=0.0,
    )
    service._stable_detected_language = None
    service.latest_tts_language = None
    service.latest_detected_language = None
    service.latest_decoder_language = None
    service.latest_detected_text = None
    service._latest_language_confidence = None
    service.phone_capture_pending = None
    class TranscriptionResult(SimpleNamespace):
        def model_copy(self, *, update):
            return TranscriptionResult(**{**vars(self), **update})

    result = TranscriptionResult(
        text="नमस्ते, मुझे मदद चाहिए।",
        language="pa",
        model_extra={
            "detected_language": "pa",
            "language_confidence": 0.82,
            "language_route": "detector",
        },
    )
    create = AsyncMock(return_value=result)
    service._client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))
    )

    transcription = await service._transcribe(b"not-a-wav")

    assert transcription.text == result.text
    assert transcription.language == "hi"
    assert service.latest_detected_language == "hi"
    assert service.latest_tts_language == "hi"
    assert service._stable_detected_language == "hi"
