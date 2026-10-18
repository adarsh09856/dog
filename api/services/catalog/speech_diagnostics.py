"""Bounded, user-supplied audio diagnostics for the local speech engine."""

import base64
import binascii
import io
import re
import time
import wave

import aiohttp

MAX_TEST_AUDIO_BYTES = 2 * 1024 * 1024

# Language codes exposed by the installed IndicConformer CTC bundle.
INDIC_STT_LANGUAGE_CODES = frozenset({
    "as", "bn", "brx", "doi", "gu", "hi", "kn", "ks", "kok", "mai", "ml",
    "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta", "te", "ur",
})


def decode_test_audio(encoded: str) -> bytes:
    if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_TEST_AUDIO_BYTES + 2) // 3):
        raise ValueError("Choose a WAV file no larger than 2 MB")
    try:
        audio = base64.b64decode(encoded, validate=True)
        if len(audio) > MAX_TEST_AUDIO_BYTES:
            raise ValueError("Choose a WAV file no larger than 2 MB")
        with wave.open(io.BytesIO(audio), "rb") as clip:
            if (clip.getcomptype() != "NONE" or clip.getsampwidth() != 2
                    or clip.getnchannels() not in (1, 2)
                    or not 8000 <= clip.getframerate() <= 48000):
                raise ValueError("Use a 16-bit PCM WAV, mono or stereo, at 8–48 kHz")
            frames = clip.getnframes()
            if not 0 < frames / clip.getframerate() <= 60:
                raise ValueError("Choose an audio clip between 0 and 60 seconds")
            if len(clip.readframes(frames)) != frames * clip.getsampwidth() * clip.getnchannels():
                raise ValueError("The WAV file is incomplete")
        return audio
    except (binascii.Error, wave.Error, EOFError) as exc:
        raise ValueError("Choose a valid 16-bit PCM WAV recording") from exc


async def transcribe_test_audio(endpoint: str, audio: bytes, model: str, language: str) -> dict:
    if not isinstance(model, str) or not model.strip() or len(model) > 200:
        raise ValueError("Select a speech recognition model")
    if not isinstance(language, str) or not re.fullmatch(r"[a-z]{2,3}|auto|multi", language):
        raise ValueError("Use a supported language code or automatic detection")
    data = aiohttp.FormData()
    data.add_field("file", audio, filename="speech-test.wav", content_type="audio/wav")
    data.add_field("model", model)
    if language not in ("auto", "multi"):
        data.add_field("language", language)
    started = time.monotonic()
    result = {"success": False, "model": model, "language": language}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.post(f"{endpoint.rstrip('/')}/audio/transcriptions", data=data) as response:
                if response.status == 200:
                    body = await response.json()
                    transcript = str(body.get("text") or "").strip()
                    result.update(success=bool(transcript), transcript=transcript)
                    if not transcript:
                        result["error"] = "No speech was recognized. Try a clear recording."
                else:
                    result["error"] = f"Speech recognition failed (HTTP {response.status})"
    except (aiohttp.ClientError, TimeoutError, ValueError):
        result["error"] = "Speech recognition is unavailable or timed out; retry with a short clip."
    result["latency_ms"] = round((time.monotonic() - started) * 1000)
    return result
