"""Offline Indic-Parler CPU service. Weights must be provisioned before startup."""
from __future__ import annotations

import asyncio
import io
import os
import threading
import wave
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

MODEL_ID = "indic-parler-tts"
SAMPLE_RATE = 24000
LANGUAGES = [f"{code}-IN" for code in (
    "as", "bn", "brx", "doi", "en", "gu", "hi", "kn", "kok", "mai",
    "ml", "mni", "mr", "ne", "or", "sa", "sat", "sd", "ta", "te", "ur",
)]
VOICES = [
    {"id": name, "name": name, "gender": gender, "accent": "Indian",
     "languages": LANGUAGES}
    for name, gender in (("Divya", "female"), ("Rohit", "male"),
                         ("Mary", "female"), ("Thoma", "male"))
]
RUNTIME = None
SYNTHESIS_LOCK = asyncio.Lock()


class SpeechRequest(BaseModel):
    model: str = MODEL_ID
    voice: str = "Divya"
    input: str = Field(min_length=1, max_length=800)
    response_format: str = "pcm"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class ParlerRuntime:
    def __init__(self):
        import torch
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer

        root = Path(os.environ.get("INDIC_PARLER_MODEL_DIR", "/models/indic-parler"))
        description_root = Path(os.environ.get(
            "INDIC_PARLER_DESCRIPTION_TOKENIZER_DIR", "/models/description-tokenizer"))
        if not (root / "config.json").is_file() or not description_root.is_dir():
            raise RuntimeError("Provision Indic-Parler weights and its description tokenizer before starting")
        torch.set_num_threads(int(os.environ.get("INDIC_PARLER_THREADS", "2")))
        torch.set_num_interop_threads(1)
        self.model = ParlerTTSForConditionalGeneration.from_pretrained(
            root, local_files_only=True, torch_dtype=torch.float32,
            low_cpu_mem_usage=True, use_safetensors=True,
            attn_implementation="sdpa").to("cpu").eval()
        self.tokenizer = AutoTokenizer.from_pretrained(root, local_files_only=True)
        self.description_tokenizer = AutoTokenizer.from_pretrained(
            description_root, local_files_only=True)

    def generate(self, request, emit, stopped):
        import soxr
        import torch
        from parler_tts import ParlerTTSStreamer
        from transformers import StoppingCriteria, StoppingCriteriaList

        model_rate = self.model.audio_encoder.config.sampling_rate
        resampler = soxr.ResampleStream(model_rate, SAMPLE_RATE, 1, dtype="float32")

        class StopOnDisconnect(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                return stopped.is_set()

        class CallbackStreamer(ParlerTTSStreamer):
            def on_finalized_audio(self, audio, stream_end=False):
                if not stopped.is_set():
                    samples = resampler.resample_chunk(
                        np.asarray(audio, dtype=np.float32), last=stream_end)
                    if samples.size:
                        emit((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())

        gender = next(voice["gender"] for voice in VOICES if voice["id"] == request.voice)
        pace = "moderate" if request.speed == 1 else ("slower" if request.speed < 1 else "faster")
        description = (f"{request.voice}, a {gender} speaker, speaks naturally in a warm "
                       f"conversational tone at a {pace} pace. Very clear close audio.")
        prompt = self.tokenizer(request.input, return_tensors="pt")
        style = self.description_tokenizer(description, return_tensors="pt")
        streamer = CallbackStreamer(
            self.model, device="cpu",
            play_steps=max(self.model.decoder.num_codebooks + 2,
                           int(self.model.audio_encoder.config.frame_rate * 0.35)))
        with torch.inference_mode():
            self.model.generate(
                input_ids=style.input_ids, attention_mask=style.attention_mask,
                prompt_input_ids=prompt.input_ids, prompt_attention_mask=prompt.attention_mask,
                streamer=streamer, do_sample=False, max_new_tokens=2048,
                stopping_criteria=StoppingCriteriaList([StopOnDisconnect()]))


@asynccontextmanager
async def lifespan(_):
    global RUNTIME
    RUNTIME = await asyncio.to_thread(ParlerRuntime)
    try:
        yield
    finally:
        RUNTIME = None


app = FastAPI(title="Kodewaves Indic-Parler CPU TTS", lifespan=lifespan)


@app.get("/health")
async def health():
    if RUNTIME is None:
        raise HTTPException(503, "Indic-Parler is not loaded")
    return {"status": "ok"}


@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{
        "id": MODEL_ID, "name": "Indic-Parler — Indian languages + English (CPU)",
        "task": "text-to-speech", "installed": True, "streaming": True,
        "languages": LANGUAGES, "experimental_languages": ["ks-IN", "pa-IN"],
        "voices": VOICES, "sample_rate": SAMPLE_RATE,
    }] if RUNTIME is not None else []}


async def pcm_stream(request):
    async with SYNTHESIS_LOCK:
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        stopped = threading.Event()

        def emit(data):
            if data and not stopped.is_set():
                loop.call_soon_threadsafe(queue.put_nowait, data)

        def generate():
            try:
                RUNTIME.generate(request, emit, stopped)
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        worker = asyncio.create_task(asyncio.to_thread(generate))
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise RuntimeError("Indic-Parler synthesis failed") from item
                yield item
        finally:
            stopped.set()
            await asyncio.shield(worker)


@app.post("/v1/audio/speech")
async def speech(request: SpeechRequest):
    if request.model != MODEL_ID:
        raise HTTPException(404, "Unknown local TTS model")
    if request.voice not in {voice["id"] for voice in VOICES}:
        raise HTTPException(400, "Select an installed Indic-Parler voice")
    if request.response_format not in {"pcm", "wav"}:
        raise HTTPException(400, "Supported formats: pcm, wav")
    if RUNTIME is None:
        raise HTTPException(503, "Indic-Parler is not loaded")
    if SYNTHESIS_LOCK.locked():
        raise HTTPException(429, "Indic-Parler is busy; retry after the current utterance")
    chunks = pcm_stream(request)
    if request.response_format == "wav":
        pcm = b"".join([chunk async for chunk in chunks])
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(SAMPLE_RATE)
            output.writeframes(pcm)
        return Response(buffer.getvalue(), media_type="audio/wav")
    # Fail before sending HTTP 200 if generation cannot produce any audio.
    try:
        first = await anext(chunks)
    except (StopAsyncIteration, RuntimeError) as exc:
        await chunks.aclose()
        raise HTTPException(502, "Indic-Parler produced no audio") from exc

    async def response():
        try:
            yield first
            async for chunk in chunks:
                yield chunk
        finally:
            await chunks.aclose()
    return StreamingResponse(response(), media_type="audio/pcm")
