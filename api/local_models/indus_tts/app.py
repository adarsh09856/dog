"""OpenAI-compatible streaming endpoint for the local Indus Pocket TTS voice."""

from __future__ import annotations

import asyncio
import importlib.util
import io
import logging
import os
import re
import time
import wave
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
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
WORKER_COUNT = max(1, min(2, int(os.environ.get("INDUS_WORKERS", "1"))))
# Bound per-call decoder batches so queued audio does not become one large chunk.
# One latent per decode keeps playback incremental when a backlog develops.
MAX_DECODER_FRAMES = max(1, min(8, int(os.environ.get("INDUS_DECODER_FRAMES", "1"))))
MODEL_POOL: list[tuple[Any, Any]] = []
AVAILABLE_MODELS: asyncio.Queue[int] = asyncio.Queue()
SYNTHESIS_WORKERS = [
    ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"local-tts-{index}")
    for index in range(WORKER_COUNT)
]
LOGGER = logging.getLogger("uvicorn.error")


def _prepare_speech_text(text: str) -> str:
    # This checkpoint ends synthesis at an internal Devanagari danda even
    # though its HTTP stream completes successfully. A comma keeps the pause
    # and lets the rest of the utterance reach the caller.
    return re.sub(r"[।॥](?=\s*\S)", ",", text)


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
    for _ in range(WORKER_COUNT):
        model, voice = module.load(int8=True, threads=1)
        model.max_decoder_frames_per_call = MAX_DECODER_FRAMES
        MODEL_POOL.append((model, voice))
    MODEL, VOICE = MODEL_POOL[0]
    global _stream_speech
    _stream_speech = module.stream


def _warm_model(model, voice) -> None:
    """Run one short Hindi/English turn before the service reports ready.

    The first generation initializes model/runtime state and can be much slower
    than subsequent streamed requests. Pay that one-time cost during startup so
    a caller does not hear it as a delayed greeting.
    """
    if model is None or voice is None or _stream_speech is None:
        raise RuntimeError("Indus TTS cannot warm up before the model is loaded")
    # Exercise both text frontends before readiness. A tiny mixed greeting
    # left the first full English request paying several seconds of lazy
    # initialization even though health already reported ready.
    for text in (
        "Hello, how can I help you today?",
        "नमस्ते, मैं आपकी कैसे मदद कर सकती हूँ?",
        "ज़रूर, you can speak in Hindi or English.",
    ):
        generator = iter(_stream_speech(model, voice, _prepare_speech_text(text)))
        has_audio = False
        try:
            for chunk in generator:
                samples = chunk.detach().cpu().numpy()
                if samples.size:
                    has_audio = True
            if not has_audio:
                raise RuntimeError("Indus TTS warm-up returned no audio")
        finally:
            close = getattr(generator, "close", None)
            if close:
                close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(_load_model)
    for index, (model, voice) in enumerate(MODEL_POOL):
        await asyncio.get_running_loop().run_in_executor(
            SYNTHESIS_WORKERS[index], _warm_model, model, voice,
        )
        AVAILABLE_MODELS.put_nowait(index)
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
        # Each autoregressive generator owns a separate model instance. The
        # upstream streaming API explicitly forbids concurrent use of one model.
        queued_at = time.monotonic()
        worker_index = await AVAILABLE_MODELS.get()
        try:
            started_at = time.monotonic()
            first_pcm_ms = None
            pcm_chunks = 0
            model, voice = MODEL_POOL[worker_index]
            worker = SYNTHESIS_WORKERS[worker_index]
            generator = iter(_stream_speech(model, voice, _prepare_speech_text(request.input)))
            def take_next():
                try:
                    return False, next(generator)
                except StopIteration:
                    return True, None

            loop = asyncio.get_running_loop()
            try:
                while True:
                    # Cancelling an await does not stop its worker thread.
                    # Serialize inference and cleanup on the same worker.
                    finished, chunk = await loop.run_in_executor(worker, take_next)
                    if finished:
                        break
                    samples = chunk.detach().cpu().numpy().astype(np.float32, copy=False)
                    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2", copy=False)
                    if pcm.size:
                        if first_pcm_ms is None:
                            first_pcm_ms = round((time.monotonic() - queued_at) * 1000)
                        pcm_chunks += 1
                        yield pcm.tobytes()
            finally:
                close = getattr(generator, "close", None)
                if close:
                    close_future = loop.run_in_executor(worker, close)
                    try:
                        await asyncio.shield(close_future)
                    except asyncio.CancelledError:
                        # Keep this model reserved until its generator really
                        # closes; an interrupted call must not race a new one.
                        await close_future
                        raise
        finally:
            AVAILABLE_MODELS.put_nowait(worker_index)
            if "started_at" in locals():
                LOGGER.info(
                    "indus_tts_request_trace chars=%s workers=%s queue_ms=%s first_pcm_ms=%s "
                    "synthesis_ms=%s total_ms=%s pcm_chunks=%s",
                    len(request.input),
                    WORKER_COUNT,
                    round((started_at - queued_at) * 1000),
                    first_pcm_ms,
                    round((time.monotonic() - started_at) * 1000),
                    round((time.monotonic() - queued_at) * 1000),
                    pcm_chunks,
                )

    if request.response_format == "wav":
        pcm = b"".join([chunk async for chunk in audio_chunks()])
        if not pcm:
            raise HTTPException(status_code=502, detail="Local TTS returned no audio")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24_000)
            output.writeframes(pcm)
        return StreamingResponse(io.BytesIO(buffer.getvalue()), media_type="audio/wav")
    chunks = audio_chunks()
    try:
        first = await anext(chunks)
    except StopAsyncIteration:
        raise HTTPException(status_code=502, detail="Local TTS returned no audio")

    async def stream():
        try:
            yield first
            async for chunk in chunks:
                yield chunk
        finally:
            await chunks.aclose()

    return StreamingResponse(stream(), media_type="audio/pcm")
