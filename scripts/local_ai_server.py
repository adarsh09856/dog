"""
Local AI Engine Runner for Kodewaves (Windows & Linux host dev)
Serves Piper Neural TTS (port 5000) and Faster-Whisper STT (port 8765).
"""

import asyncio
import re
import io
import os
import sys
import wave
import tempfile
import threading
from pathlib import Path
from typing import Optional, Dict, Any

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse

# Paths
VOICE_DIR = Path(os.environ.get("PIPER_DATA_DIR", str(Path.home() / "piper_data")))
VOICE_DIR.mkdir(parents=True, exist_ok=True)

# Cache loaded models
LOADED_PIPER_VOICES: Dict[str, Any] = {}
LOADED_WHISPER_MODELS: Dict[str, Any] = {}
PIPER_LOCK = threading.RLock()
WHISPER_LOCK = threading.RLock()


def validate_voice_id(value: str) -> str:
    voice_id = value.removesuffix(".onnx")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", voice_id):
        raise HTTPException(status_code=400, detail="Invalid voice ID")
    return voice_id


def whisper_model_id(value: Optional[str]) -> str:
    chosen = (value or "tiny").removeprefix("Systran/faster-whisper-")
    if chosen not in ("tiny", "base", "small"):
        raise HTTPException(status_code=400, detail="Unsupported Whisper model")
    return chosen


# ==============================================================================
# 1. PIPER TTS SERVICE (Port 5000)
# ==============================================================================
piper_app = FastAPI(title="Kodewaves Local Piper TTS Service")
piper_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_piper_voice(voice_name: str):
    from piper import PiperVoice

    voice_key = validate_voice_id(voice_name)
    if voice_key in LOADED_PIPER_VOICES:
        return LOADED_PIPER_VOICES[voice_key]

    model_path = VOICE_DIR / f"{voice_key}.onnx"
    if not model_path.is_file() or not model_path.with_suffix(".onnx.json").is_file():
        raise HTTPException(status_code=404, detail=f"Voice model {voice_key} is not installed. Download it first.")

    voice = PiperVoice.load(str(model_path))
    LOADED_PIPER_VOICES[voice_key] = voice
    return voice


@piper_app.get("/voices")
async def list_voices():
    voices = []
    for onnx_file in VOICE_DIR.glob("*.onnx"):
        if not onnx_file.with_suffix(".onnx.json").is_file():
            continue
        voice_id = onnx_file.stem
        voices.append({
            "id": voice_id,
            "key": voice_id,
            "name": voice_id,
            "installed": True,
            "model_path": str(onnx_file),
        })
    return {"voices": voices, "status": "online"}


@piper_app.post("/synthesize")
@piper_app.post("/")
async def synthesize(request: Request):
    payload = await request.json()
    text = payload.get("text") or payload.get("input") or "Hello"
    voice_name = payload.get("voice") or "hi_IN-pratham-medium"

    def synthesize_sync():
        with PIPER_LOCK:
            voice = get_piper_voice(voice_name)
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(voice.config.sample_rate)
                for chunk in voice.synthesize(text):
                    wav_file.writeframes(chunk.audio_int16_bytes)
            return wav_io.getvalue()

    wav_bytes = await asyncio.to_thread(synthesize_sync)
    return Response(content=wav_bytes, media_type="audio/wav")


@piper_app.post("/download")
async def download_voice_endpoint(payload: Dict[str, Any]):
    voice_id = payload.get("voice")
    if not voice_id:
        raise HTTPException(status_code=400, detail="Missing voice parameter")
    from piper.download_voices import download_voice
    voice_id = validate_voice_id(voice_id)
    def download_sync():
        with PIPER_LOCK:
            download_voice(voice_id, VOICE_DIR)
            LOADED_PIPER_VOICES.pop(voice_id, None)
    await asyncio.to_thread(download_sync)
    return {"success": True, "voice": voice_id, "message": f"Voice {voice_id} downloaded"}


@piper_app.delete("/voices/{voice_id}")
async def delete_voice_endpoint(voice_id: str):
    voice_id = validate_voice_id(voice_id)
    def delete_sync():
        with PIPER_LOCK:
            LOADED_PIPER_VOICES.pop(voice_id, None)
            (VOICE_DIR / f"{voice_id}.onnx").unlink(missing_ok=True)
            (VOICE_DIR / f"{voice_id}.onnx.json").unlink(missing_ok=True)
    await asyncio.to_thread(delete_sync)
    return {"success": True, "message": f"Voice {voice_id} deleted"}


# ==============================================================================
# 2. FASTER-WHISPER STT SERVICE (Port 8765)
# ==============================================================================
whisper_app = FastAPI(title="Kodewaves Local Faster-Whisper STT Service")
whisper_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_whisper_model(model_name: Optional[str] = None):
    from faster_whisper import WhisperModel

    chosen = whisper_model_id(model_name)

    if chosen in LOADED_WHISPER_MODELS:
        return LOADED_WHISPER_MODELS[chosen]

    model = WhisperModel(chosen, device="cpu", compute_type="int8")
    LOADED_WHISPER_MODELS[chosen] = model
    return model


@whisper_app.get("/health")
async def whisper_health():
    return {"status": "ok", "service": "faster-whisper", "device": "cpu"}


@whisper_app.get("/models")
@whisper_app.get("/v1/models")
async def whisper_models():
    return {
        "object": "list",
        "data": [
            {"id": f"Systran/faster-whisper-{name}", "name": f"Faster-Whisper {name}", "owned_by": "systran",
             "task": "automatic-speech-recognition", "installed": name in LOADED_WHISPER_MODELS}
            for name in ("tiny", "base", "small")
        ],
    }


async def load_whisper_model(model_name: Optional[str]):
    chosen = whisper_model_id(model_name)

    def preload_sync():
        with WHISPER_LOCK:
            get_whisper_model(chosen)

    await asyncio.to_thread(preload_sync)
    return {"success": True, "model": chosen}


@whisper_app.post("/models")
@whisper_app.post("/v1/models")
async def preload_whisper(payload: Dict[str, Any]):
    return await load_whisper_model(payload.get("model"))


@whisper_app.post("/models/{model_id:path}")
@whisper_app.post("/v1/models/{model_id:path}")
async def preload_whisper_by_id(model_id: str):
    return await load_whisper_model(model_id)


@whisper_app.delete("/models/{model_id:path}")
@whisper_app.delete("/v1/models/{model_id:path}")
async def unload_whisper(model_id: str):
    chosen = whisper_model_id(model_id)
    def unload_sync():
        with WHISPER_LOCK:
            LOADED_WHISPER_MODELS.pop(chosen, None)
    await asyncio.to_thread(unload_sync)
    return {"success": True, "message": f"Model {chosen} unloaded"}


@whisper_app.post("/audio/transcriptions")
@whisper_app.post("/v1/audio/transcriptions")
async def transcribe_audio(
    file: UploadFile = File(...),
    model: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
):
    whisper_model_id(model)
    contents = await file.read()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    lang = language if (language and language not in ("auto", "default", "multi")) else None
    def transcribe_sync():
        # The worker owns the file: cancelling the HTTP request cannot stop its
        # thread, so request-level cleanup could delete audio before it is read.
        try:
            with WHISPER_LOCK:
                model_instance = get_whisper_model(model)
                segments, info = model_instance.transcribe(tmp_path, language=lang, beam_size=1, vad_filter=True)
                transcript_text = " ".join(seg.text.strip() for seg in segments).strip()
                return {"text": transcript_text, "language": info.language,
                        "language_probability": info.language_probability, "duration": info.duration}
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    return await asyncio.to_thread(transcribe_sync)


def run_piper():
    uvicorn.run(piper_app, host="127.0.0.1", port=5000, log_level="warning")


def run_whisper():
    uvicorn.run(whisper_app, host="127.0.0.1", port=8765, log_level="warning")


if __name__ == "__main__":
    t_piper = threading.Thread(target=run_piper, daemon=True)
    t_whisper = threading.Thread(target=run_whisper, daemon=True)
    t_piper.start()
    t_whisper.start()
    print("Local AI Runner active: Piper TTS on http://127.0.0.1:5000, Faster-Whisper on http://127.0.0.1:8765")
    t_piper.join()
    t_whisper.join()
