"""Self-hosted DhVaani speech endpoint with explicit, licensed voice references.

The service reports installed only after the gated checkpoint and at least one
reference voice load. No remote inference provider is used for synthesis.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

MODEL_ID = "dhvaani-0.5"
MODEL_REPO = "ARTPARK-IISc/DhVaani-0.5"
MODEL_REVISION = os.environ.get("DHVAANI_MODEL_REVISION", "main")
MODEL_DIR = Path(os.environ.get("DHVAANI_MODEL_DIR", "/models/dhvaani"))
VOICE_DIR = Path(os.environ.get("DHVAANI_VOICE_DIR", "/voices"))
SAMPLE_RATE = 24_000
NUM_STEPS = int(os.environ.get("DHVAANI_NUM_STEPS", "16"))
INDIAN_LANGUAGES = (
    "as", "bn", "brx", "doi", "gu", "hi", "kn", "kok", "ks", "mai",
    "ml", "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta",
    "te", "ur",
)
SUPPORTED_LANGUAGES = [*(f"{code}-IN" for code in INDIAN_LANGUAGES), "en-IN"]
MODEL = None
VOICES: dict[str, dict] = {}
WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dhvaani")
LOCK = asyncio.Lock()


def _load_voices() -> dict[str, dict]:
    manifest = VOICE_DIR / "voices.json"
    if not manifest.is_file():
        raise RuntimeError("DhVaani voice references are missing")
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("DhVaani needs at least one reference voice")
    voices = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError("Invalid DhVaani voice entry")
        voice_id = entry.get("id")
        filename = entry.get("file")
        transcript = entry.get("transcript")
        gender = entry.get("gender")
        if not all(isinstance(v, str) and v.strip() for v in (voice_id, filename, transcript)):
            raise RuntimeError("DhVaani voice needs id, file and transcript")
        if gender not in {"male", "female", "unknown"}:
            raise RuntimeError("DhVaani voice gender must be explicit")
        if voice_id in voices or Path(filename).name != filename:
            raise RuntimeError("Duplicate voice or invalid reference filename")
        reference = VOICE_DIR / filename
        if not reference.is_file():
            raise RuntimeError(f"Missing DhVaani reference: {filename}")
        with wave.open(str(reference), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                raise RuntimeError(f"DhVaani reference must be mono PCM16: {filename}")
            seconds = wav.getnframes() / wav.getframerate()
            if not 3 <= seconds <= 10:
                raise RuntimeError(f"DhVaani reference must be 3–10 seconds: {filename}")
        voices[voice_id] = {
            "id": voice_id, "name": entry.get("name") or voice_id,
            "gender": gender, "accent": entry.get("accent") or "Indian multilingual",
            "languages": SUPPORTED_LANGUAGES, "preview_text": entry.get("preview_text") or transcript,
            "file": str(reference), "transcript": transcript,
        }
    return voices


def _load() -> None:
    global MODEL, VOICES
    import torch
    from transformers import AutoModel

    voices = _load_voices()
    torch.set_num_threads(max(1, int(os.environ.get("DHVAANI_THREADS", "2"))))
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model = AutoModel.from_pretrained(
        MODEL_REPO, revision=MODEL_REVISION, cache_dir=str(MODEL_DIR),
        trust_remote_code=True, token=os.environ.get("HF_TOKEN"),
    ).to("cpu").eval()
    if int(model.sampling_rate) != SAMPLE_RATE:
        raise RuntimeError("DhVaani returned an unexpected sample rate")
    MODEL, VOICES = model, voices


@asynccontextmanager
async def lifespan(_app):
    await asyncio.get_running_loop().run_in_executor(WORKER, _load)
    yield


app = FastAPI(title="Kodewaves DhVaani Local Speech", lifespan=lifespan)


class SpeechRequest(BaseModel):
    model: str = MODEL_ID
    voice: str
    input: str = Field(min_length=1, max_length=360)
    response_format: str = "pcm"
    speed: float = Field(default=1.0, ge=0.75, le=1.25)


@app.get("/health")
async def health():
    if MODEL is None or not VOICES:
        raise HTTPException(503, "DhVaani is not ready")
    return {"status": "ok"}


@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{
        "id": MODEL_ID, "name": "DhVaani 0.5 — 22 Indian languages + English (CPU)",
        "task": "text-to-speech", "installed": MODEL is not None and bool(VOICES),
        "streaming": False, "sample_rate": SAMPLE_RATE,
        "languages": SUPPORTED_LANGUAGES,
        "voices": [{key: value for key, value in voice.items() if key not in {"file", "transcript"}}
                   for voice in VOICES.values()],
    }]}


def _synthesize(text: str, voice: dict, speed: float) -> bytes:
    import torch

    if MODEL is None:
        raise RuntimeError("DhVaani is not loaded")
    with torch.inference_mode():
        samples = MODEL.synthesize(
            text=text, prompt_wav=voice["file"], prompt_text=voice["transcript"],
            num_step=NUM_STEPS, guidance_scale=1.0, speed=speed,
        )
    samples = np.asarray(samples, dtype=np.float32).reshape(-1)
    if not samples.size or not np.isfinite(samples).all():
        raise RuntimeError("DhVaani returned invalid audio")
    return (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()


@app.post("/v1/audio/speech")
async def speech(request: SpeechRequest):
    if request.model != MODEL_ID:
        raise HTTPException(404, "Unknown local TTS model")
    if request.voice not in VOICES:
        raise HTTPException(400, "Select an installed DhVaani voice")
    if request.response_format not in {"pcm", "wav"}:
        raise HTTPException(400, "Supported formats: pcm, wav")
    if not request.input.strip():
        raise HTTPException(400, "Speech text must contain words")
    if MODEL is None:
        raise HTTPException(503, "DhVaani is loading")
    started = time.perf_counter()
    async with LOCK:
        synthesis_started = time.perf_counter()
        future = asyncio.get_running_loop().run_in_executor(
            WORKER, _synthesize, request.input.strip(), VOICES[request.voice], request.speed,
        )
        try:
            pcm = await asyncio.shield(future)
        except asyncio.CancelledError:
            # Native CPU synthesis cannot stop mid-call. Keep the lock until
            # it finishes so a cancelled turn cannot leave work queued ahead
            # of the next user's speech.
            try:
                await future
            except Exception:
                pass
            raise
        except Exception as exc:
            raise HTTPException(502, f"DhVaani synthesis failed: {exc}") from exc
    completed = time.perf_counter()
    headers = {
        "X-TTS-Queue-Ms": str(round((synthesis_started - started) * 1000)),
        "X-TTS-Synthesis-Ms": str(round((completed - synthesis_started) * 1000)),
        "X-TTS-Audio-Ms": str(round(len(pcm) / 2 / SAMPLE_RATE * 1000)),
    }
    if request.response_format == "pcm":
        return Response(pcm, media_type="audio/pcm", headers=headers)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return Response(buffer.getvalue(), media_type="audio/wav", headers=headers)
