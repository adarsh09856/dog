"""CPU IndicConformer and English Moonshine STT with an OpenAI-compatible API.

Models are downloaded at installation/startup, never during a call. Only installed
languages appear in /v1/models. The caller must select a language explicitly;
this service does not identify the language or decode mixed-language speech.
"""

from __future__ import annotations

import asyncio
import io
import os
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np
import sherpa_onnx
import soundfile as sf
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from huggingface_hub import hf_hub_download

REPOSITORY = "parismitaglobalsolutions/indicconformer-sherpa-onnx"
REVISION = "9721eb71eea141fae0982cfcdb9dd2e3d4953c4a"
ENGLISH_REPOSITORY = "csukuangfj/sherpa-onnx-moonshine-tiny-en-int8"
ENGLISH_REVISION = "bf2b762c076d8ea61e2af0b3851c9564fb77552e"
ENGLISH_FILES = (
    "preprocess.onnx", "encode.int8.onnx", "uncached_decode.int8.onnx",
    "cached_decode.int8.onnx", "tokens.txt", "LICENSE",
)
MODEL_ID = "indicconformer-ctc-int8"
INDIC_LANGUAGES = frozenset({
    "as", "bn", "brx", "doi", "gu", "hi", "kn", "ks", "kok", "mai", "ml",
    "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta", "te", "ur",
})
LANGUAGES = INDIC_LANGUAGES | {"en"}
MODEL_DIR = Path(os.environ.get("INDIC_STT_MODEL_DIR", "/models/indicconformer"))
PRELOAD = os.environ.get("INDIC_STT_LANGUAGES", "hi").strip().lower()
THREADS = max(1, int(os.environ.get("INDIC_STT_THREADS", "2")))

app = FastAPI(title="Kodewaves Indic CPU STT")
_loaded: OrderedDict[str, sherpa_onnx.OfflineRecognizer] = OrderedDict()
_inference_lock = asyncio.Lock()
_max_resident_models = max(1, int(os.environ.get("INDIC_STT_RESIDENT_MODELS", "2")))


def _installed_languages() -> list[str]:
    installed = {
        lang for lang in INDIC_LANGUAGES
        if (MODEL_DIR / lang / "model.int8.onnx").is_file()
        and (MODEL_DIR / "tokens.txt").is_file()
    }
    if all((MODEL_DIR / "en" / filename).is_file() for filename in ENGLISH_FILES):
        installed.add("en")
    return sorted(installed)


def _download_models(languages: set[str]) -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    indic_languages = languages & INDIC_LANGUAGES
    if indic_languages:
        hf_hub_download(repo_id=REPOSITORY, revision=REVISION, filename="tokens.txt", local_dir=MODEL_DIR)
        for lang in sorted(indic_languages):
            hf_hub_download(
                repo_id=REPOSITORY,
                revision=REVISION,
                filename=f"{lang}/model.int8.onnx",
                local_dir=MODEL_DIR,
            )
    if "en" in languages and not all((MODEL_DIR / "en" / name).is_file() for name in ENGLISH_FILES):
        for filename in ENGLISH_FILES:
            hf_hub_download(
                repo_id=ENGLISH_REPOSITORY,
                revision=ENGLISH_REVISION,
                filename=filename,
                local_dir=MODEL_DIR / "en",
            )


def _load(lang: str) -> sherpa_onnx.OfflineRecognizer:
    recognizer = _loaded.get(lang)
    if recognizer is not None:
        _loaded.move_to_end(lang)
        return recognizer
    if lang == "en":
        english = MODEL_DIR / "en"
        recognizer = sherpa_onnx.OfflineRecognizer.from_moonshine(
            preprocessor=str(english / "preprocess.onnx"),
            encoder=str(english / "encode.int8.onnx"),
            uncached_decoder=str(english / "uncached_decode.int8.onnx"),
            cached_decoder=str(english / "cached_decode.int8.onnx"),
            tokens=str(english / "tokens.txt"),
            num_threads=THREADS,
        )
    else:
        recognizer = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
            model=str(MODEL_DIR / lang / "model.int8.onnx"),
            tokens=str(MODEL_DIR / "tokens.txt"),
            num_threads=THREADS,
            decoding_method="greedy_search",
        )
    # Keep the previous recognizer if a new model fails to load. The inference
    # lock serializes decoding; a brief extra model during this swap fits the
    # bounded STT container, while only two remain resident afterward.
    while len(_loaded) >= _max_resident_models:
        _loaded.popitem(last=False)
    _loaded[lang] = recognizer
    return recognizer


@app.on_event("startup")
async def startup() -> None:
    languages = LANGUAGES if PRELOAD == "all" else set(PRELOAD.split(","))
    if not languages or not languages <= LANGUAGES:
        raise RuntimeError("INDIC_STT_LANGUAGES contains an unsupported language")
    await asyncio.to_thread(_download_models, languages)
    # A small CPU host must not keep 22 recognizers resident simultaneously.
    await asyncio.to_thread(_load, "hi" if "hi" in languages else sorted(languages)[0])
    if "en" in languages and _max_resident_models > 1:
        # Keep both main caller languages ready without first-call model loading.
        await asyncio.to_thread(_load, "en")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok" if _loaded else "starting", "installed_languages": _installed_languages()}


@app.get("/v1/models")
async def models() -> dict:
    return {"object": "list", "data": [{
        "id": MODEL_ID,
        "task": "automatic-speech-recognition",
        "installed": bool(_installed_languages()),
        "languages": [f"{lang}-IN" for lang in _installed_languages()],
    }] if _installed_languages() else []}


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form(MODEL_ID),
    language: str = Form(...),
) -> dict:
    if model != MODEL_ID:
        raise HTTPException(status_code=404, detail="Unknown local STT model")
    lang = language.strip().lower().replace("_", "-").split("-", 1)[0]
    if lang not in _installed_languages():
        raise HTTPException(status_code=400, detail="Selected Indic STT language is not installed")
    payload = await file.read(5_000_001)
    if len(payload) > 5_000_000:
        raise HTTPException(status_code=413, detail="Audio exceeds 5 MB")
    try:
        waveform, sample_rate = sf.read(io.BytesIO(payload), dtype="float32")
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid audio file") from exc
    if waveform.ndim == 2:
        waveform = waveform.mean(axis=1)
    if waveform.ndim != 1 or not np.isfinite(waveform).all():
        raise HTTPException(status_code=400, detail="Invalid audio samples")
    if sample_rate < 8000 or sample_rate > 48000:
        raise HTTPException(status_code=400, detail="Unsupported sample rate")
    if len(waveform) < sample_rate // 10 or float(np.sqrt(np.mean(waveform * waveform))) < 0.003:
        # CTC can turn digital silence into isolated letters. Let the call
        # remain idle rather than sending invented speech to the agent.
        return {"text": "", "language": lang, "duration_ms": 0}

    def decode() -> str:
        recognizer = _load(lang)
        stream = recognizer.create_stream()
        stream.accept_waveform(sample_rate, waveform)
        recognizer.decode_stream(stream)
        return stream.result.text.strip()

    async with _inference_lock:
        started = time.monotonic()
        text = await asyncio.to_thread(decode)
    return {"text": text, "language": lang, "duration_ms": round((time.monotonic() - started) * 1000)}
