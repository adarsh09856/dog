import pytest
import io
import wave
from array import array
from openai.types.audio import Transcription

from api.services.pipecat.speaches_stt import BoundedSpeachesSTTService
from api.services.pipecat.speaches_stt import _normalize_quiet_pcm16_wav
from pipecat.services.speaches.stt import SpeachesSTTService
from types import SimpleNamespace
from unittest.mock import AsyncMock


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
