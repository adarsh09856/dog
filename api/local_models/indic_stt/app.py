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
import re
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
PREWARM = os.environ.get("INDIC_STT_PREWARM_LANGUAGES", "").strip().lower()
THREADS = max(1, int(os.environ.get("INDIC_STT_THREADS", "2")))
LID_ENABLED = os.environ.get("INDIC_STT_AUTO_DETECT", "1").strip().lower() not in {"0", "false", "no"}
LID_THREADS = max(1, int(os.environ.get("INDIC_STT_LID_THREADS", "2")))

_PHONE_DIGIT_WORDS = {
    "zero": "0", "oh": "0", "shunya": "0", "शून्य": "0", "जीरो": "0",
    "one": "1", "एक": "1", "वन": "1", "ओन": "1", "two": "2", "दो": "2", "टू": "2", "three": "3",
    "तीन": "3", "थ्री": "3", "four": "4", "चार": "4", "फोर": "4",
    "five": "5", "पांच": "5", "पाँच": "5", "फाइव": "5", "six": "6",
    "छह": "6", "सिक्स": "6", "seven": "7", "सात": "7", "सेवन": "7",
    "eight": "8", "आठ": "8", "एट": "8", "ऐट": "8", "nine": "9", "नौ": "9", "ज़ीरो": "0",
    "नाइन": "9", "double": "double", "डबल": "double", "ડબલ": "double", "டபுள்": "double",
    # Keep the rescue scorer aligned with the call-side phone parser: Hindi
    # ASR often renders English digit names phonetically in Devanagari.
    "नीन": "9", "निन": "9", "नान": "9", "नाईन": "9",
    "थी": "3", "आइट": "8", "आईट": "8",
    # Match the call-scoped phone parser's explicit regional spellings. Without
    # these, a valid regional-script primary decode can look like zero digits
    # and incorrectly lose to a poorer English rescue candidate.
    "শূন্য": "0", "এক": "1", "দুই": "2", "তিন": "3", "চার": "4",
    "পাঁচ": "5", "ছয়": "6", "সাত": "7", "আট": "8", "নয়": "9",
    "பூஜ்யம்": "0", "ஒன்று": "1", "இரண்டு": "2", "மூன்று": "3", "நான்கு": "4",
    "ஐந்து": "5", "ஆறு": "6", "ஏழு": "7", "எட்டு": "8", "ஒன்பது": "9",
    "సున్నా": "0", "ఒకటి": "1", "రెండు": "2", "మూడు": "3", "నాలుగు": "4",
    "ఐదు": "5", "ఆరు": "6", "ఏడు": "7", "ఎనిమిది": "8", "తొమ్మిది": "9",
    "ಸೊನ್ನೆ": "0", "ಒಂದು": "1", "ಎರಡು": "2", "ಮೂರು": "3", "ನಾಲ್ಕು": "4",
    "ಐದು": "5", "ಆರು": "6", "ಏಳು": "7", "ಎಂಟು": "8", "ಒಂಬತ್ತು": "9",
    "പൂജ്യം": "0", "ഒന്ന്": "1", "രണ്ട്": "2", "മൂന്ന്": "3", "നാല്": "4",
    "അഞ്ച്": "5", "ആറ്": "6", "ഏഴ്": "7", "എട്ട്": "8", "ഒൻപത്": "9",
    "ਸਿਫ਼ਰ": "0", "ਇੱਕ": "1", "ਦੋ": "2", "ਤਿੰਨ": "3", "ਚਾਰ": "4",
    "ਪੰਜ": "5", "ਛੇ": "6", "ਸੱਤ": "7", "ਅੱਠ": "8", "ਨੌਂ": "9",
    "दोन": "2", "पाच": "5", "सहा": "6", "नऊ": "9",
    # Phonetic Gujarati and Tamil renderings of English digit words accepted
    # by the call-side parser must count as primary-recognizer evidence too.
    "નાઇન": "9", "નાઈટ": "9", "ફાઇવ": "5", "ફાઈવ": "5",
    "થ્રી": "3", "એઇટ": "8", "એઈટ": "8", "ફોર": "4", "વન": "1",
    "જીરો": "0", "ઝીરો": "0",
    "நைன்": "9",
    "ஜீரோ": "0", "ஜிரோ": "0", "ஃபோர்": "4", "ஃபைவ்": "5",
    "பைவ்": "5", "த்ரீ": "3", "எய்ட்": "8", "ஏய்ட்": "8",
    "ஏஐட்": "8",
}


def _phone_digit_count(text: str) -> int:
    """Count explicit digit groups without interpreting general number words."""
    tokens = [
        token.strip("()[]{}\"'")
        for token in re.split(r"[\s,.!?।॥:;\-–—]+", str(text or "").casefold())
        if token.strip("()[]{}\"'")
    ]
    count = 0
    repeat_next = False
    for token in tokens:
        if token.isdecimal():
            count += len(token)
            repeat_next = False
            continue
        value = _PHONE_DIGIT_WORDS.get(token)
        if value == "double":
            repeat_next = True
        elif value is not None:
            count += 2 if repeat_next else 1
            repeat_next = False
        else:
            repeat_next = False
    return count


def _phone_rescue_is_better(primary: str, english: str) -> bool:
    """Use an English candidate only when it recovers a clear digit sequence."""
    english_digits = _phone_digit_count(english)
    return english_digits >= 3 and english_digits > _phone_digit_count(primary)

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
    # Installed languages and resident languages are different budgets. Allow
    # regional deployments to choose their warm decoders without restricting
    # the installed inventory or silently evicting one during startup.
    if PREWARM:
        warm_languages = list(dict.fromkeys(code.strip() for code in PREWARM.split(",")))
        if not set(warm_languages) <= languages:
            raise RuntimeError("INDIC_STT_PREWARM_LANGUAGES must contain installed languages")
        if len(warm_languages) > _max_resident_models:
            raise RuntimeError("INDIC_STT_PREWARM_LANGUAGES exceeds INDIC_STT_RESIDENT_MODELS")
    else:
        warm_languages = ["hi" if "hi" in languages else sorted(languages)[0]]
        if "en" in languages and "en" not in warm_languages and _max_resident_models > 1:
            warm_languages.append("en")
    await asyncio.to_thread(_download_models, languages)
    for lang in warm_languages:
        await asyncio.to_thread(_load, lang)
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
    phone_capture: bool = Form(False),
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

    def decode(language_code: str) -> str:
        recognizer = _load(language_code)
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
        text = await asyncio.to_thread(decode, lang)
        primary_phone_digits = _phone_digit_count(text) if phone_capture else 0
        primary_number_complete = 10 <= primary_phone_digits <= 15
        if (
            phone_capture
            and lang == "hi"
            and not primary_number_complete
            and "en" in installed
            and "en" in _loaded
        ):
            # English digit words are frequently code-switched into Hindi calls.
            # The primary Hindi result remains the fallback unless the already
            # resident Moonshine decoder recovers more explicit digit content.
            english_text = await asyncio.to_thread(decode, "en")
            if _phone_rescue_is_better(text, english_text):
                text = english_text
                language_route = "phone_english_rescue"
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
