"""OpenAI-compatible streaming endpoint for the local Indus Pocket TTS voice."""

from __future__ import annotations

import asyncio
import importlib.util
import io
import os
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from huggingface_hub import snapshot_download
from pydantic import BaseModel, Field

MODEL_ID = "indus-pocket-tts"
MODEL_REPO = "Indus-Labs/indus-pocket-tts"
MODEL_REVISION = "39899d3c1dcda47a7ef167cd222419feb86abeb9"
MODEL_DIR = Path(os.environ.get("INDUS_MODEL_DIR", "/models/indus-pocket-tts"))
MODEL: Any = None
VOICE: Any = None
_stream_speech: Any = None
SYNTHESIS_LOCK = asyncio.Lock()


def _load_model() -> None:
    global MODEL, VOICE
    model_dir = Path(
        snapshot_download(repo_id=MODEL_REPO, revision=MODEL_REVISION, local_dir=str(MODEL_DIR))
    )
    speak_path = model_dir / "speak.py"
    spec = importlib.util.spec_from_file_location("indus_pocket_speak", speak_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Indus TTS model package is missing speak.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    MODEL, VOICE = module.load(int8=True, threads=1)
    global _stream_speech
    _stream_speech = module.stream


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(_load_model)
    yield


app = FastAPI(title="Kodewaves Local Indian TTS", lifespan=lifespan)


class SpeechRequest(BaseModel):
    model: str = MODEL_ID
    voice: str = "Inaya"
    input: str = Field(min_length=1, max_length=1200)
    response_format: str = "pcm"
    speed: float = 1.0


@app.get("/health")
async def health():
    return {"status": "ok" if MODEL is not None else "starting"}


@app.get("/v1/models")
async def models():
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_ID,
                "name": "Indus Pocket TTS — Hindi/Hinglish (CPU)",
                "object": "model",
                "task": "text-to-speech",
                "installed": MODEL is not None,
                "languages": ["hi-IN", "en-IN"],
                "voices": [
                    {
                        "id": "Inaya",
                        "name": "Inaya — Indian Hindi and Hinglish",
                        "gender": "female",
                        "accent": "Indian",
                        "languages": ["hi-IN", "en-IN"],
                        "preview_text": "नमस्ते, मैं आपकी कैसे मदद कर सकती हूँ? You can also speak in English.",
                    }
                ],
            }
        ],
    }


@app.post("/v1/audio/speech")
async def speech(request: SpeechRequest):
    if request.model != MODEL_ID:
        raise HTTPException(status_code=404, detail="Unknown local TTS model")
    if request.voice.casefold() not in {"inaya", "default"}:
        raise HTTPException(status_code=400, detail="This model supports the Inaya voice")
    if request.response_format not in {"pcm", "wav"}:
        raise HTTPException(status_code=400, detail="Supported formats: pcm, wav")
    if MODEL is None:
        raise HTTPException(status_code=503, detail="Local TTS model is loading")

    async def audio_chunks():
        # A single autoregressive generator is kept on this one-CPU service so
        # concurrent calls do not multiply latency or RAM use on small hosts.
        async with SYNTHESIS_LOCK:
            generator = iter(_stream_speech(MODEL, VOICE, request.input))
            while True:
                def take_next():
                    try:
                        return False, next(generator)
                    except StopIteration:
                        return True, None

                finished, chunk = await asyncio.to_thread(take_next)
                if finished:
                    break
                samples = chunk.detach().cpu().numpy().astype(np.float32, copy=False)
                pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2", copy=False)
                if pcm.size:
                    yield pcm.tobytes()

    if request.response_format == "wav":
        pcm = b"".join([chunk async for chunk in audio_chunks()])
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24_000)
            output.writeframes(pcm)
        return StreamingResponse(io.BytesIO(buffer.getvalue()), media_type="audio/wav")
    return StreamingResponse(audio_chunks(), media_type="audio/pcm")
