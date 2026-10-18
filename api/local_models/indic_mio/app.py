"""OpenAI-compatible, local CPU endpoint for Indic-Mio LiteRT TTS."""

from __future__ import annotations

import asyncio
import ctypes
import io
import os
import wave
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from huggingface_hub import snapshot_download
from pydantic import BaseModel, Field

MODEL_ID = "indic-mio-tts"
MODEL_NAME = "Indic-Mio 0.6B — 22 Indian languages + English (CPU, buffered)"
MODEL_REPO = "soniqo/Indic-Mio-LiteRT"
MODEL_REVISION = "8c9c7589872ad637a5ee725cd20d4b63e0f86e24"
MODEL_DIR = Path(os.environ.get("INDIC_MIO_MODEL_DIR", "/models/indic-mio"))
SAMPLE_RATE = 24_000
INDIAN_LANGUAGES = [
    "as-IN", "bn-IN", "brx-IN", "doi-IN", "gu-IN", "hi-IN", "ks-IN",
    "kn-IN", "kok-IN", "mai-IN", "ml-IN", "mni-IN", "mr-IN", "ne-IN",
    "or-IN", "pa-IN", "sa-IN", "sat-IN", "sd-IN", "ta-IN", "te-IN", "ur-IN",
]
SUPPORTED_LANGUAGES = [*INDIAN_LANGUAGES, "en-IN"]
MODEL: ctypes.CDLL | None = None
HANDLE: int | None = None
MAX_TEXT_TOKENS = 64
SYNTHESIS_LOCK = asyncio.Lock()
SYNTHESIS_WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="indic-mio")

ChunkCallback = ctypes.CFUNCTYPE(
    None, ctypes.POINTER(ctypes.c_float), ctypes.c_size_t, ctypes.c_bool, ctypes.c_void_p
)


def _load_model() -> None:
    global MODEL, HANDLE, MAX_TEXT_TOKENS
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    bundle = Path(snapshot_download(
        repo_id=MODEL_REPO,
        revision=MODEL_REVISION,
        local_dir=str(MODEL_DIR),
        allow_patterns=[
            "indicmio-text-prefill.tflite", "indicmio-token-step.tflite",
            "indicmio-audio-decoder.tflite", "indicmio-ref-encoder.tflite",
            "tokenizer.json", "config.json",
        ],
    ))
    lib = ctypes.CDLL("/opt/speech-core/libspeech_core_models_litert.so")
    lib.sc_indic_mio_create.argtypes = [ctypes.c_char_p]
    lib.sc_indic_mio_create.restype = ctypes.c_void_p
    lib.sc_indic_mio_destroy.argtypes = [ctypes.c_void_p]
    lib.sc_indic_mio_set_max_new_tokens.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.sc_indic_mio_set_temperature.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.sc_indic_mio_set_top_p.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.sc_indic_mio_set_top_k.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.sc_indic_mio_synthesize.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ChunkCallback, ctypes.c_void_p]
    lib.sc_indic_mio_synthesize.restype = ctypes.c_int
    lib.sc_indic_mio_last_error.argtypes = [ctypes.c_void_p]
    lib.sc_indic_mio_last_error.restype = ctypes.c_char_p
    lib.sc_indic_mio_max_text_tokens.argtypes = [ctypes.c_void_p]
    lib.sc_indic_mio_max_text_tokens.restype = ctypes.c_int
    handle = lib.sc_indic_mio_create(str(bundle).encode())
    if not handle:
        raise RuntimeError("LiteRT could not load the Indic-Mio model bundle")
    lib.sc_indic_mio_set_max_new_tokens(handle, 256)
    lib.sc_indic_mio_set_temperature(handle, 0.85)
    lib.sc_indic_mio_set_top_p(handle, 0.9)
    lib.sc_indic_mio_set_top_k(handle, 50)
    MAX_TEXT_TOKENS = lib.sc_indic_mio_max_text_tokens(handle)
    MODEL, HANDLE = lib, handle


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(_load_model)
    try:
        yield
    finally:
        if MODEL is not None and HANDLE is not None:
            MODEL.sc_indic_mio_destroy(HANDLE)


app = FastAPI(title="Kodewaves Indic-Mio CPU TTS", lifespan=lifespan)


class SpeechRequest(BaseModel):
    model: str = MODEL_ID
    voice: str = "default"
    input: str = Field(min_length=1, max_length=1200)
    response_format: str = "pcm"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


@app.get("/health")
async def health():
    return {"status": "ok" if HANDLE is not None else "starting"}


@app.get("/v1/models")
async def models():
    return {
        "object": "list",
        "data": [{
            "id": MODEL_ID,
            "name": MODEL_NAME,
            "object": "model",
            "task": "text-to-speech",
            "installed": HANDLE is not None,
            "streaming": False,
            "languages": SUPPORTED_LANGUAGES,
            "voices": [{
                "id": "default",
                "name": "Indic-Mio default voice",
                "gender": "unknown",
                "accent": "Indian multilingual",
                "languages": SUPPORTED_LANGUAGES,
                "preview_text": "नमस्ते, मैं आपकी कैसे मदद कर सकती हूँ? Hello, how can I help you?",
            }],
        }],
    }


def _synthesize(text: str) -> bytes:
    if MODEL is None or HANDLE is None:
        raise RuntimeError("Indic-Mio is not loaded")
    chunks: list[np.ndarray] = []

    @ChunkCallback
    def collect(samples, length, _is_final, _context):
        if length:
            # C++ owns this memory only through the callback; copy immediately.
            chunks.append(np.ctypeslib.as_array(samples, shape=(length,)).copy())

    code = MODEL.sc_indic_mio_synthesize(HANDLE, text.encode("utf-8"), collect, None)
    if code != 0:
        detail = MODEL.sc_indic_mio_last_error(HANDLE).decode("utf-8", errors="replace")
        raise RuntimeError(detail or "Indic-Mio synthesis failed")
    if not chunks:
        raise RuntimeError("Indic-Mio returned no audio")
    pcm = np.concatenate(chunks)
    pcm16 = (np.clip(pcm, -1.0, 1.0) * 32767.0).astype("<i2", copy=False)
    return pcm16.tobytes()


@app.post("/v1/audio/speech")
async def speech(request: SpeechRequest):
    if request.model != MODEL_ID:
        raise HTTPException(status_code=404, detail="Unknown local TTS model")
    if request.voice.casefold() not in {"default", "indic-mio-default"}:
        raise HTTPException(status_code=400, detail="Indic-Mio currently exposes its default multilingual voice")
    if request.response_format not in {"pcm", "wav"}:
        raise HTTPException(status_code=400, detail="Supported formats: pcm, wav")
    if HANDLE is None:
        raise HTTPException(status_code=503, detail="Indic-Mio is loading its local model bundle")
    if len(request.input.split()) > MAX_TEXT_TOKENS:
        raise HTTPException(status_code=400, detail=f"Split this utterance into shorter sentences (maximum {MAX_TEXT_TOKENS} text tokens)")
    async with SYNTHESIS_LOCK:
        try:
            pcm = await asyncio.get_running_loop().run_in_executor(SYNTHESIS_WORKER, _synthesize, request.input)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Indic-Mio synthesis failed: {exc}") from exc
    if request.speed != 1.0:
        # Preserve the configured speaking rate by changing playback duration;
        # this also changes pitch slightly. Keep the DSP deterministic and CPU-light.
        signal = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
        target_length = max(1, round(len(signal) / request.speed))
        old_axis = np.arange(len(signal), dtype=np.float64)
        new_axis = np.linspace(0, len(signal) - 1, target_length)
        pcm = np.interp(new_axis, old_axis, signal).astype("<i2").tobytes()
    if request.response_format == "pcm":
        return Response(content=pcm, media_type="audio/pcm")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm)
    return Response(content=buffer.getvalue(), media_type="audio/wav")
