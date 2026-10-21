"""Local AI4Bharat VITS Rasa speech, with truthful per-speaker capabilities."""
from __future__ import annotations

import asyncio
import io
import os
import threading
import unicodedata
import wave
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import sherpa_onnx
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from huggingface_hub import hf_hub_download
from pydantic import BaseModel, Field

MODEL_ID = "indic-vits-rasa-13"
MODEL_REPO = "MatiasLin/sherpa-onnx-vits-rasa-13"
MODEL_REVISION = "b5afd4e991e3bdd6195528de650e2ed219d47506"
MODEL_DIR = Path(os.environ.get("INDIC_VITS_MODEL_DIR", "/models/indic-vits-rasa-13"))
THREADS = max(1, int(os.environ.get("INDIC_VITS_THREADS", "2")))
SAMPLE_RATE = 24_000
# Only documented trained speaker slots, not the embedding's 1024-slot capacity.
# https://huggingface.co/ai4bharat/vits_rasa_13#speaker-style-identifier-overview
SPEAKERS = {
    "ASM_F": (0, "as", "Assamese", "female"),
    "ASM_M": (1, "as", "Assamese", "male"),
    "BEN_F": (2, "bn", "Bengali", "female"),
    "BEN_M": (3, "bn", "Bengali", "male"),
    "BRX_F": (4, "brx", "Bodo", "female"),
    "BRX_M": (5, "brx", "Bodo", "male"),
    "DOI_F": (6, "doi", "Dogri", "female"),
    "DOI_M": (7, "doi", "Dogri", "male"),
    "KAN_F": (8, "kn", "Kannada", "female"),
    "KAN_M": (9, "kn", "Kannada", "male"),
    "MAI_M": (10, "mai", "Maithili", "male"),
    "MAL_F": (11, "ml", "Malayalam", "female"),
    "MAR_F": (12, "mr", "Marathi", "female"),
    "MAR_M": (13, "mr", "Marathi", "male"),
    "NEP_F": (14, "ne", "Nepali", "female"),
    "PAN_F": (15, "pa", "Punjabi", "female"),
    "PAN_M": (16, "pa", "Punjabi", "male"),
    "SAN_M": (17, "sa", "Sanskrit", "male"),
    "TAM_F": (18, "ta", "Tamil", "female"),
    "TEL_F": (19, "te", "Telugu", "female"),
}
# These scripts identify a language served by this checkpoint without
# confusing shared Devanagari or Bengali-Assamese scripts for a single language.
SCRIPT_VOICES = (
    (0x0A00, 0x0A7F, "pa"),  # Gurmukhi
    (0x0B80, 0x0BFF, "ta"),
    (0x0C00, 0x0C7F, "te"),
    (0x0C80, 0x0CFF, "kn"),
    (0x0D00, 0x0D7F, "ml"),
)


def voice_for_text(text: str, preferred_voice: str) -> str:
    """Use a matching installed voice for unambiguous regional script.

    The selected voice supplies the preferred gender. A missing gender or
    ambiguous script keeps the explicitly selected voice; neither is guessed.
    """
    counts: dict[str, int] = {}
    for character in text:
        code = ord(character)
        for start, end, language in SCRIPT_VOICES:
            if start <= code <= end:
                counts[language] = counts.get(language, 0) + 1
                break
    if not counts:
        return preferred_voice
    language = max(counts, key=counts.get)
    gender = SPEAKERS[preferred_voice][3]
    return next((voice for voice, (_, lang, _, speaker_gender) in SPEAKERS.items()
                 if lang == language and speaker_gender == gender), preferred_voice)
PREVIEWS = {
    "as": "নমস্কাৰ, মই আপোনাক কেনেকৈ সহায় কৰিব পাৰোঁ",
    "bn": "নমস্কার, আমি আপনাকে কীভাবে সাহায্য করতে পারি",
    "brx": "रावजों, आं नोंखौ माबोरै मदद होनो हायो",
    "doi": "नमस्कार, तुसेंगी केह् मदद चाहिदी ऐ",
    "kn": "ನಮಸ್ಕಾರ, ನಿಮಗೆ ಯಾವ ಸಹಾಯ ಬೇಕು",
    "mai": "नमस्कार, अहाँ केहन सहायता चाहैत छी",
    "ml": "നമസ്കാരം, നിങ്ങൾക്ക് എന്ത് സഹായമാണ് വേണ്ടത്",
    "mr": "नमस्कार, तुम्हाला कोणत्या मदतीची गरज आहे",
    "ne": "नमस्कार, तपाईंलाई कस्तो सहयोग चाहिएको छ",
    "pa": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਤੁਹਾਨੂੰ ਕਿਸ ਚੀਜ਼ ਵਿੱਚ ਮਦਦ ਚਾਹੀਦੀ ਹੈ",
    "sa": "नमस्कारः, भवते किम् साहाय्यम् अपेक्षितम्",
    "ta": "வணக்கம், உங்களுக்கு என்ன உதவி வேண்டும்",
    "te": "నమస్కారం, మీకు ఏ సహాయం కావాలి",
}
MODEL = None
WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="indic-vits")
LOCK = asyncio.Lock()


def _pcm(samples) -> bytes:
    samples = np.asarray(samples, dtype=np.float32)
    if not samples.size or not np.isfinite(samples).all():
        raise RuntimeError("Local voice returned invalid audio")
    return (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()


def _generate(text: str, voice: str, speed: float, callback=None) -> bytes:
    config = sherpa_onnx.GenerationConfig()
    config.sid = SPEAKERS[voice_for_text(text, voice)][0]
    config.speed = speed
    config.extra = {"emotion_id": "4"}  # Documented CONV (conversational) style.
    # This exported character model produces a noisy extra utterance for trailing
    # sentence punctuation in sherpa's sentence splitter. Preserve internal breaks.
    text = unicodedata.normalize("NFC", text).strip().rstrip(".!?।॥ \n")
    if not text:
        raise ValueError("Speech text must contain words")
    audio = MODEL.generate(text, config, callback) if callback else MODEL.generate(text, config)
    if audio.sample_rate != SAMPLE_RATE:
        raise RuntimeError("Local voice returned invalid audio")
    return _pcm(audio.samples)


async def stream_pcm(request):
    """Forward native sentence callbacks while synthesis is still running."""
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()
    stopped = threading.Event()
    emitted = False

    def callback(samples, _progress):
        nonlocal emitted
        if stopped.is_set():
            return 0
        chunk = _pcm(samples)
        emitted = True
        loop.call_soon_threadsafe(queue.put_nowait, chunk)
        # Measured sherpa-onnx 1.13.8 behavior: 1 continues, 0 cancels.
        return 1

    async with LOCK:
        future = loop.run_in_executor(
            WORKER, _generate, request.input, request.voice, request.speed, callback)
        future.add_done_callback(lambda _: queue.put_nowait(None))
        try:
            while (chunk := await queue.get()) is not None:
                yield chunk
            pcm = await asyncio.shield(future)
            if not emitted:
                yield pcm
        finally:
            stopped.set()
            # Native inference may outlive an HTTP disconnect. Keep ownership
            # until it stops so a new request cannot queue behind stale work.
            if not future.done():
                await asyncio.shield(future)


def _load() -> None:
    global MODEL
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for filename in ("model.onnx", "tokens.txt"):
        if not (MODEL_DIR / filename).is_file():
            hf_hub_download(MODEL_REPO, filename, revision=MODEL_REVISION, local_dir=MODEL_DIR)
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(MODEL_DIR / "model.onnx"), tokens=str(MODEL_DIR / "tokens.txt")),
            num_threads=THREADS, provider="cpu"), max_num_sentences=1)
    MODEL = sherpa_onnx.OfflineTts(config)
    _generate(PREVIEWS["ta"], "TAM_F", 1.0)


@asynccontextmanager
async def lifespan(_app):
    await asyncio.get_running_loop().run_in_executor(WORKER, _load)
    yield


app = FastAPI(title="Kodewaves Regional Indian CPU Speech", lifespan=lifespan)


class SpeechRequest(BaseModel):
    model: str = MODEL_ID
    voice: str  # Do not silently substitute a different language or gender.
    input: str = Field(min_length=1, max_length=600)
    response_format: str = "pcm"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


@app.get("/health")
async def health():
    if MODEL is None:
        raise HTTPException(503, "Regional voice is loading")
    return {"status": "ok"}


@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{
        "id": MODEL_ID, "name": "AI4Bharat VITS Rasa — 13 Indian languages (CPU)",
        "task": "text-to-speech", "installed": MODEL is not None,
        "streaming": True, "streaming_granularity": "sentence", "sample_rate": SAMPLE_RATE,
        "languages": sorted({f"{speaker[1]}-IN" for speaker in SPEAKERS.values()}),
        "attribution": "AI4Bharat VITS Rasa, CC BY 4.0; ONNX export by MatiasLin",
        "voices": [{"id": voice, "name": f"{name} — {gender.title()}",
                    "gender": gender, "accent": f"Indian {name}",
                    "languages": [f"{lang}-IN"], "preview_text": PREVIEWS[lang]}
                   for voice, (_sid, lang, name, gender) in SPEAKERS.items()],
    }]}


@app.post("/v1/audio/speech")
async def speech(request: SpeechRequest):
    if request.model != MODEL_ID:
        raise HTTPException(404, "Unknown local TTS model")
    if request.voice not in SPEAKERS:
        raise HTTPException(400, "Select a documented regional voice")
    if request.response_format not in {"pcm", "wav"}:
        raise HTTPException(400, "Supported formats: pcm, wav")
    if not request.input.strip().rstrip(".!?।॥ \n"):
        raise HTTPException(400, "Speech text must contain words")
    if MODEL is None:
        raise HTTPException(503, "Regional voice is loading")
    if request.response_format == "pcm":
        return StreamingResponse(stream_pcm(request), media_type="audio/pcm")
    async with LOCK:
        future = asyncio.get_running_loop().run_in_executor(
            WORKER, _generate, request.input, request.voice, request.speed)
        try:
            pcm = await asyncio.shield(future)
        except asyncio.CancelledError:
            # The native CPU call continues after HTTP cancellation. Finish it
            # before releasing the lock so repeated calls cannot queue stale work.
            await future
            raise
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return Response(buffer.getvalue(), media_type="audio/wav")
