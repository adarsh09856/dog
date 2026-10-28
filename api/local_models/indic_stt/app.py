"""CPU IndicConformer and English Moonshine STT with an OpenAI-compatible API.

Models are downloaded at installation/startup, never during a call. Only installed
languages appear in /v1/models. An optional CPU language identifier can choose the
language-specific decoder for each utterance; it does not decode code-switching
inside a single utterance.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np
import sherpa_onnx
import soundfile as sf
import soxr
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
LID_REPOSITORY = "CIIL/Anuvani-LID"
LID_REVISION = "3b9caa41c0a5ec5a09d38f3aecb2fa1dd6602531"
LID_FILENAME = "mobile_inference/models/anuvani_lid.int8.onnx"
LID_LABELS = (
    "assamese", "bengali", "bodo", "dogri", "english", "gujarati", "hindi",
    "kannada", "kashmiri", "konkani", "maithili", "malayalam", "manipuri",
    "marathi", "nepali", "odia", "punjabi", "sanskrit", "santali", "sindhi",
    "tamil", "telugu", "urdu",
)
LID_LANGUAGE_CODES = (
    "as", "bn", "brx", "doi", "en", "gu", "hi", "kn", "ks", "kok", "mai",
    "ml", "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta", "te", "ur",
)
# Keep the recognizer's product language inventory explicit. The LID model has
# extra classes, but these eight languages are intentionally not exposed in
# Kodewaves. Detection of an excluded class falls back to the caller's last
# supported language (or Hindi) rather than returning Urdu text or a 422.
AUTO_DETECT_LANGUAGES = frozenset({
    "as", "bn", "brx", "doi", "en", "hi", "kn", "mai", "ml", "mr",
    "ne", "pa", "sa", "ta", "te",
})
SCHEDULED_INDIAN_LANGUAGES = AUTO_DETECT_LANGUAGES - {"en"}
AUTO_LANGUAGE_MIN_CONFIDENCE = 0.65
AUTO_ENGLISH_MIN_CONFIDENCE = 0.50
# CIIL's Anuvani-LID paper calibrates the released 23-class logits with T=0.674.
# The ONNX graph returns logits, so calibration must happen before softmax.
LID_TEMPERATURE = 0.674
INDIC_LANGUAGES = SCHEDULED_INDIAN_LANGUAGES
LANGUAGES = AUTO_DETECT_LANGUAGES
MODEL_DIR = Path(os.environ.get("INDIC_STT_MODEL_DIR", "/models/indicconformer"))
PRELOAD = os.environ.get("INDIC_STT_LANGUAGES", "hi").strip().lower()
THREADS = max(1, int(os.environ.get("INDIC_STT_THREADS", "2")))
LID_ENABLED = os.environ.get("INDIC_STT_AUTO_DETECT", "1").strip().lower() not in {"0", "false", "no"}
LID_THREADS = max(1, int(os.environ.get("INDIC_STT_LID_THREADS", "2")))

app = FastAPI(title="Kodewaves Indic CPU STT")
_loaded: OrderedDict[str, sherpa_onnx.OfflineRecognizer] = OrderedDict()
_inference_lock = asyncio.Lock()
_max_resident_models = max(1, int(os.environ.get("INDIC_STT_RESIDENT_MODELS", "2")))
_lid_session = None
_english_lid = None
_logger = logging.getLogger("uvicorn.error")


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
    # Evict before constructing the next graph. Loading first can temporarily
    # keep max_resident_models + 1 recognizers alive, which exceeds the 2-GiB
    # production container limit when callers switch languages.
    while len(_loaded) >= _max_resident_models:
        # With three slots, reserve the already-loaded Hindi and English
        # recognizers and rotate regional languages through the other slots.
        # Smaller installations retain ordinary LRU eviction so every
        # installed language remains usable.
        protected = {"hi", "en"} if _max_resident_models >= 3 else set()
        victim = next((name for name in _loaded if name not in protected), None)
        if victim is None:
            _evicted_language, evicted_recognizer = _loaded.popitem(last=False)
        else:
            evicted_recognizer = _loaded.pop(victim)
        del evicted_recognizer
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
    _loaded[lang] = recognizer
    return recognizer


def _warm_recognizer(lang: str) -> None:
    """Run one short synthetic decode so first callers avoid cold graph setup."""
    recognizer = _load(lang)
    sample_rate = 16_000
    index = np.arange(sample_rate, dtype=np.float32)
    waveform = (
        0.01 * np.sin(2 * np.pi * 173 * index / sample_rate)
        + 0.005 * np.sin(2 * np.pi * 431 * index / sample_rate)
    ).astype(np.float32, copy=False)
    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate, waveform)
    recognizer.decode_stream(stream)


@app.on_event("startup")
async def startup() -> None:
    global _lid_session, _english_lid
    languages = LANGUAGES if PRELOAD == "all" else set(PRELOAD.split(","))
    if not languages or not languages <= LANGUAGES:
        raise RuntimeError("INDIC_STT_LANGUAGES contains an unsupported language")
    await asyncio.to_thread(_download_models, languages)
    # A small CPU host must not keep 22 recognizers resident simultaneously.
    await asyncio.to_thread(_load, "hi" if "hi" in languages else sorted(languages)[0])
    if "en" in languages and _max_resident_models > 1:
        # Keep both main caller languages ready without first-call model loading.
        await asyncio.to_thread(_load, "en")
    warm_languages = [lang for lang in ("hi", "en") if lang in _loaded]
    for lang in warm_languages:
        warmup_started = time.monotonic()
        await asyncio.to_thread(_warm_recognizer, lang)
        _logger.info(
            "stt_decoder_warmup_ms=%s language=%s",
            round((time.monotonic() - warmup_started) * 1000),
            lang,
        )
    if LID_ENABLED:
        try:
            await asyncio.to_thread(_load_language_identifier)
            warmup_started = time.monotonic()
            await asyncio.to_thread(_warm_language_identifiers)
            _logger.info(
                "auto_language_identifier_warmup_ms=%s english_rescue=%s",
                round((time.monotonic() - warmup_started) * 1000),
                _english_lid is not None,
            )
        except Exception:
            # Explicit-language recognition must stay available if the optional
            # detector cannot be fetched, initialized, or warmed before use.
            _lid_session = None
            _english_lid = None
            _logger.exception("Auto language detection is unavailable")


@app.get("/health")
async def health() -> dict:
    installed = [
        language for language in _installed_languages()
        if language in AUTO_DETECT_LANGUAGES
    ]
    return {
        "status": "ok" if _loaded else "starting",
        "installed_languages": installed,
        "resident_languages": list(_loaded),
        "supports_auto_detect": _lid_session is not None,
        "auto_detect_languages": [
            code for code in LID_LANGUAGE_CODES
            if code in installed and code in AUTO_DETECT_LANGUAGES
        ]
        if _lid_session is not None else [],
    }


@app.get("/v1/models")
async def models() -> dict:
    installed = [
        language for language in _installed_languages()
        if language in AUTO_DETECT_LANGUAGES
    ]
    return {"object": "list", "data": [{
        "id": MODEL_ID,
        "task": "automatic-speech-recognition",
        "installed": bool(installed),
        "languages": [f"{lang}-IN" for lang in installed],
        "supports_auto_detect": _lid_session is not None,
        "auto_detect_languages": [
            code for code in LID_LANGUAGE_CODES
            if code in installed and code in AUTO_DETECT_LANGUAGES
        ]
        if _lid_session is not None else [],
    }] if installed else []}


def _load_language_identifier() -> None:
    global _lid_session, _english_lid
    import onnxruntime as ort

    model_path = hf_hub_download(
        repo_id=LID_REPOSITORY,
        revision=LID_REVISION,
        filename=LID_FILENAME,
        local_dir=MODEL_DIR / "lid",
    )
    options = ort.SessionOptions()
    options.intra_op_num_threads = LID_THREADS
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    _lid_session = ort.InferenceSession(
        model_path,
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    whisper_dir = MODEL_DIR / "lid" / "whisper_tiny"
    encoder = whisper_dir / "tiny-encoder.int8.onnx"
    decoder = whisper_dir / "tiny-decoder.int8.onnx"
    if encoder.is_file() and decoder.is_file():
        _english_lid = sherpa_onnx.SpokenLanguageIdentification(
            sherpa_onnx.SpokenLanguageIdentificationConfig(
                whisper=sherpa_onnx.SpokenLanguageIdentificationWhisperConfig(
                    encoder=str(encoder), decoder=str(decoder),
                ),
                num_threads=1,
                provider="cpu",
            )
        )


def _warm_language_identifiers() -> None:
    """Run detector inference before readiness so callers do not pay cold graph cost."""
    if _lid_session is None:
        raise RuntimeError("The local language identifier is not available")

    # Use a deterministic non-speech signal; never store or log caller audio.
    # Four seconds exercises the primary ONNX graph at ordinary turn lengths.
    sample_rate = 16_000
    index = np.arange(sample_rate * 4, dtype=np.float32)
    audio = (
        0.01 * np.sin(2 * np.pi * 173 * index / sample_rate)
        + 0.005 * np.sin(2 * np.pi * 431 * index / sample_rate)
    ).astype(np.float32, copy=False)
    _detected, _confidence, detection_route = _detect_language(audio, sample_rate)

    # The English rescue normally runs only when the primary model predicts a
    # non-English class. Warm it explicitly so readiness does not depend on the
    # synthetic signal's predicted class.
    if _english_lid is not None and detection_route not in {
        "whisper_english_rescue",
        "competitive_indian_english",
    } and _detected == "en":
        stream = _english_lid.create_stream()
        stream.accept_waveform(sample_rate, audio)
        _english_lid.compute(stream)


def _calibrated_log_probabilities(logits: np.ndarray) -> np.ndarray:
    """Apply the released Anuvani-LID temperature to raw ONNX logits."""
    calibrated = np.asarray(logits, dtype=np.float64) / LID_TEMPERATURE
    shifted = calibrated - float(np.max(calibrated))
    return shifted - float(np.log(np.exp(shifted).sum()))


def _detect_language(waveform: np.ndarray, sample_rate: int) -> tuple[str, float, str | None]:
    """Return the dominant supported language and its calibrated model score."""
    session = _lid_session
    if session is None:
        raise RuntimeError("The local language identifier is not available")

    audio = np.asarray(waveform, dtype=np.float32)
    if sample_rate != 16000:
        audio = soxr.resample(audio, sample_rate, 16000, quality="HQ").astype(np.float32, copy=False)
    if audio.size < 1600:
        raise ValueError("Speech is too short to identify a language")

    max_piece_samples = 30 * 16000
    pieces = [audio[start:start + max_piece_samples] for start in range(0, audio.size, max_piece_samples)]
    if len(pieces) > 1 and pieces[-1].size < 16000:
        # Avoid making a language decision from a tiny tail; use a full window
        # ending at the end of the recording, as the model's serving guidance does.
        pieces[-1] = audio[-max_piece_samples:]

    weighted_log_probabilities = np.zeros(len(LID_LABELS), dtype=np.float64)
    total_weight = 0
    for piece in pieces:
        # The released model's verified ONNX contract requires 512 zero samples
        # after the true audio length for its final mel frames.
        padded = np.pad(piece, (0, 512)).astype(np.float32, copy=False)
        logits = session.run(None, {
            "audio": padded[None, :],
            "audio_length": np.asarray([piece.size], dtype=np.int64),
        })[0][0]
        logits = np.asarray(logits, dtype=np.float64)
        if logits.shape != (len(LID_LABELS),) or not np.isfinite(logits).all():
            raise RuntimeError("The local language identifier returned invalid scores")
        log_probabilities = _calibrated_log_probabilities(logits)
        weight = int(piece.size)
        weighted_log_probabilities += log_probabilities * weight
        total_weight += weight
    mean_log_probabilities = weighted_log_probabilities / total_weight
    probabilities = np.exp(mean_log_probabilities - float(np.max(mean_log_probabilities)))
    probabilities /= float(np.sum(probabilities))
    index = int(np.argmax(probabilities))
    detected = LID_LANGUAGE_CODES[index]
    # Anuvani often classifies Indian-accented English as Hindi or Telugu.
    # A second, independent detector may rescue English, while its regional
    # predictions are deliberately ignored because they are less reliable.
    if detected != "en" and _english_lid is not None and audio.size >= 16000:
        stream = _english_lid.create_stream()
        stream.accept_waveform(16000, audio[: 10 * 16000])
        if _english_lid.compute(stream) == "en":
            english_probability = float(probabilities[LID_LANGUAGE_CODES.index("en")])
            return "en", english_probability, "whisper_english_rescue"
    # Indian-accented English can rank just below Hindi even in a clearly
    # English utterance. Strong Hindi examples have negligible English mass;
    # rescue only this close hi/en pair, leaving regional routes untouched.
    if detected == "hi" and audio.size >= 16000:
        english_probability = float(probabilities[LID_LANGUAGE_CODES.index("en")])
        if float(probabilities[index]) < 0.85 and english_probability >= 0.10:
            return "en", english_probability, "competitive_indian_english"
    return detected, float(probabilities[index]), None


def _resolve_decode_language(
    detected: str,
    confidence: float,
    fallback_language: str | None,
    installed: set[str],
    detection_route: str | None = None,
) -> tuple[str, str]:
    """Choose an installed decoder without silently relabeling clear speech."""
    detected = str(detected or "").lower().replace("_", "-").split("-", 1)[0]
    fallback = str(fallback_language or "").lower().replace("_", "-").split("-", 1)[0]
    supported = installed & AUTO_DETECT_LANGUAGES
    if detected not in supported:
        if detected in LID_LANGUAGE_CODES and detected not in AUTO_DETECT_LANGUAGES:
            # Do not expose or decode excluded languages. Reuse the established
            # supported language when available; otherwise use Hindi, then
            # English, so an auto-detected utterance still receives a final.
            if fallback in supported:
                return fallback, "excluded_language_to_previous_supported"
            if "hi" in supported:
                return "hi", "excluded_language_to_hindi"
            if "en" in supported:
                return "en", "excluded_language_to_english"
            if supported:
                return sorted(supported)[0], "excluded_language_to_first_supported"
            raise RuntimeError("No supported automatic STT language is installed")
        threshold = AUTO_ENGLISH_MIN_CONFIDENCE if detected == "en" else AUTO_LANGUAGE_MIN_CONFIDENCE
        if confidence >= threshold:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "unsupported_detected_language",
                    "language": detected,
                    "message": (
                        "Speech was confidently detected in a language that is not "
                        "enabled for this self-hosted speech route."
                    ),
                },
            )
        if fallback in supported:
            return fallback, "unsupported_language_held_previous"
        if "hi" in supported:
            return "hi", "unsupported_language_to_hindi"
        if "en" in supported:
            return "en", "unsupported_language_to_english"
        if supported:
            return sorted(supported)[0], "unsupported_language_to_first_supported"
        raise RuntimeError("No supported automatic STT language is installed")
    if detection_route in {"competitive_indian_english", "whisper_english_rescue"} and detected == "en":
        return "en", detection_route
    threshold = AUTO_ENGLISH_MIN_CONFIDENCE if detected == "en" else AUTO_LANGUAGE_MIN_CONFIDENCE
    if confidence < threshold and fallback in supported:
        return fallback, "held_previous_low_confidence"
    return detected, "detector_english" if detected == "en" else "detector"


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form(MODEL_ID),
    language: str | None = Form(None),
    fallback_language: str | None = Form(None),
) -> dict:
    if model != MODEL_ID:
        raise HTTPException(status_code=404, detail="Unknown local STT model")
    requested_language = (language or "auto").strip().lower().replace("_", "-").split("-", 1)[0]
    auto_detect = requested_language in {"", "auto", "multi", "default", "unknown"}
    installed = _installed_languages()
    if auto_detect and _lid_session is None:
        raise HTTPException(status_code=503, detail="Local automatic language detection is unavailable")
    lang = requested_language
    fallback = (fallback_language or "").strip().lower().replace("_", "-").split("-", 1)[0]
    if fallback not in installed:
        fallback = ""
    if not auto_detect and lang not in installed:
        raise HTTPException(status_code=400, detail="Selected Indic STT language is not installed")
    if not auto_detect and lang not in AUTO_DETECT_LANGUAGES:
        raise HTTPException(status_code=400, detail="Selected Indic STT language is not enabled")
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
        return {"text": "", "language": lang if not auto_detect else "", "duration_ms": 0}

    def decode() -> str:
        recognizer = _load(lang)
        stream = recognizer.create_stream()
        stream.accept_waveform(sample_rate, waveform)
        recognizer.decode_stream(stream)
        return stream.result.text.strip()

    request_started = time.monotonic()
    async with _inference_lock:
        started = time.monotonic()
        language_confidence = None
        detected_language = None
        language_route = "configured"
        lid_started = time.monotonic()
        if auto_detect:
            try:
                detected_language, language_confidence, detection_route = await asyncio.to_thread(
                    _detect_language, waveform, sample_rate
                )
            except ValueError:
                return {"text": "", "language": "", "duration_ms": 0}
            lang, language_route = _resolve_decode_language(
                detected_language, language_confidence, fallback or None, set(installed), detection_route
            )
            if lang not in installed:
                raise HTTPException(status_code=503, detail="Selected STT language is not installed on this engine")
        lid_ms = round((time.monotonic() - lid_started) * 1000) if auto_detect else 0
        decode_started = time.monotonic()
        text = await asyncio.to_thread(decode)
        decode_ms = round((time.monotonic() - decode_started) * 1000)
    duration_ms = round((time.monotonic() - started) * 1000)
    _logger.info(
        "indic_stt_request_trace auto=%s language=%s route=%s queue_ms=%s lid_ms=%s "
        "decode_ms=%s duration_ms=%s",
        auto_detect,
        lang,
        language_route,
        round((started - request_started) * 1000),
        lid_ms,
        decode_ms,
        duration_ms,
    )
    response = {
        "text": text,
        "language": lang,
        "duration_ms": duration_ms,
    }
    if language_confidence is not None:
        response["language_confidence"] = round(language_confidence, 4)
        response["detected_language"] = detected_language
        response["language_route"] = language_route
    return response
