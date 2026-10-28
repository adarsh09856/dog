"""Check the readiness and voice contract without downloading gated weights."""
import json
import asyncio
import threading
import wave

import pytest
import httpx

from api.local_models.dhvaani import app as dhvaani


def _reference(path, seconds=3.5):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(b"\0\0" * int(16_000 * seconds))


def test_voice_manifest_requires_transcribed_reference(tmp_path, monkeypatch):
    _reference(tmp_path / "female.wav")
    (tmp_path / "voices.json").write_text(json.dumps([{
        "id": "indian-female", "file": "female.wav", "gender": "female",
        "transcript": "Hello, how can I help you?",
    }]), encoding="utf-8")
    monkeypatch.setattr(dhvaani, "VOICE_DIR", tmp_path)
    voices = dhvaani._load_voices()
    assert voices["indian-female"]["file"] == str(tmp_path / "female.wav")
    assert "en-IN" in voices["indian-female"]["languages"]
    assert "hi-IN" in voices["indian-female"]["languages"]
    assert "kn-IN" in voices["indian-female"]["languages"]


def test_voice_manifest_rejects_short_or_missing_reference(tmp_path, monkeypatch):
    _reference(tmp_path / "short.wav", seconds=1)
    (tmp_path / "voices.json").write_text(json.dumps([{
        "id": "short", "file": "short.wav", "gender": "female", "transcript": "Hello",
    }]), encoding="utf-8")
    monkeypatch.setattr(dhvaani, "VOICE_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="3–10 seconds"):
        dhvaani._load_voices()


def test_unloaded_model_is_not_advertised(monkeypatch):
    monkeypatch.setattr(dhvaani, "MODEL", None)
    monkeypatch.setattr(dhvaani, "VOICES", {})
    inventory = asyncio.run(dhvaani.models())
    assert inventory["data"][0]["installed"] is False
    assert inventory["data"][0]["voices"] == []


@pytest.mark.asyncio
async def test_speech_route_uses_selected_local_voice(monkeypatch):
    monkeypatch.setattr(dhvaani, "MODEL", object())
    monkeypatch.setattr(dhvaani, "VOICES", {
        "indian-female": {"id": "indian-female", "file": "/voices/female.wav",
                          "transcript": "Hello", "gender": "female"},
    })
    seen = []

    def fake_synthesize(text, voice, speed):
        seen.append((text, voice["id"], speed))
        return b"\0\0" * 240

    monkeypatch.setattr(dhvaani, "_synthesize", fake_synthesize)
    transport = httpx.ASGITransport(app=dhvaani.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await client.post("/v1/audio/speech", json={
            "model": "dhvaani-0.5", "voice": "indian-female",
            "input": " Hello ", "response_format": "pcm", "speed": 1.0,
        })
        assert result.status_code == 200
        assert result.content == b"\0\0" * 240
        assert result.headers["x-tts-audio-ms"] == "10"
        assert int(result.headers["x-tts-synthesis-ms"]) >= 0
        assert seen == [("Hello", "indian-female", 1.0)]
        missing = await client.post("/v1/audio/speech", json={
            "model": "dhvaani-0.5", "voice": "wrong", "input": "Hello",
        })
        assert missing.status_code == 400


@pytest.mark.asyncio
async def test_cancelled_turn_holds_cpu_slot_until_synthesis_exits(monkeypatch):
    monkeypatch.setattr(dhvaani, "MODEL", object())
    monkeypatch.setattr(dhvaani, "VOICES", {"female": {
        "id": "female", "file": "/voices/female.wav", "transcript": "Hello",
    }})
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def fake_synthesize(text, _voice, _speed):
        calls.append(text)
        if text == "first":
            entered.set()
            assert release.wait(3)
        return b"\0\0" * 240

    monkeypatch.setattr(dhvaani, "_synthesize", fake_synthesize)
    first = asyncio.create_task(dhvaani.speech(dhvaani.SpeechRequest(voice="female", input="first")))
    assert await asyncio.to_thread(entered.wait, 2)
    first.cancel()
    second = asyncio.create_task(dhvaani.speech(dhvaani.SpeechRequest(voice="female", input="second")))
    await asyncio.sleep(0.03)
    assert calls == ["first"]
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert (await second).body == b"\0\0" * 240
    assert calls == ["first", "second"]
