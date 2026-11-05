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

try:
    from api.local_models.indic_stt.spoken_digits import (
        PHONE_SCORING_DIGITS as _PHONE_DIGIT_WORDS,
        count_spoken_phone_digits as _phone_digit_count,
    )
except ModuleNotFoundError:  # Standalone image copies this shared file beside app.py.
    from spoken_digits import (
        PHONE_SCORING_DIGITS as _PHONE_DIGIT_WORDS,
        count_spoken_phone_digits as _phone_digit_count,
    )

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
# Speech recognition advertises the languages this service can decode. Reply
# language/voice routing is separately constrained by the active TTS voice's
# installed capability contract in the API pipeline.
AUTO_DETECT_LANGUAGES = frozenset(LID_LANGUAGE_CODES)
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

def _phone_decode_has_unknown_tokens(text: str) -> bool:
    """Return whether a phone-slot decode contains non-digit, unknown words.

    Phone speech is often code-switched, so a partial Hindi decode with an
    English phonetic fragment (or vice versa) is a useful signal to try the
    already-resident alternate decoder. Common number-introduction words are
    ignored so callers can say "my phone number is ..." without triggering a
    rescue solely because of the preamble.
    """
    return _phone_unknown_token_count(text) > 0


_PHONE_CONTEXT_RE = re.compile(
    r"\b(?:my\s+)?(?:phone|mobile|number)\b|"
    r"(?:मेरा|मेरे)?\s*(?:फोन|मोबाइल|नंबर|नम्बर)",
    re.IGNORECASE,
)
_NON_PHONE_CONTEXT_RE = re.compile(
    r"\b(?:appointment|booking|book|schedule|date|time|today|tomorrow|"
    r"yesterday|morning|afternoon|evening|help|later|after)\b|"
    r"अपॉइंटमेंट|अप्पॉइंटमेंट|बुकिंग|बुक|तारीख|समय|कल|आज|सुबह|दोपहर|शाम|बजे|मदद|सहायता|बाद",
    re.IGNORECASE,
)


def _should_try_phone_rescue(text: str) -> bool:
    """Rescue only plausible phone utterances, not arbitrary speech in a phone slot.

    While phone collection is pending, a caller can still correct intent or
    answer another question. A single number word (for example Hindi "एक")
    inside an appointment sentence must not make an alternate decoder reinterpret
    the whole sentence as a phone number.
    """
    digits = _phone_digit_count(text)
    if digits > 15:
        return True
    if not _phone_decode_has_unknown_tokens(text):
        return False
    if _NON_PHONE_CONTEXT_RE.search(text):
        return False
    if _PHONE_CONTEXT_RE.search(text):
        return True
    return digits >= 3


def _phone_unknown_token_count(text: str) -> int:
    """Count non-number tokens in a phone decode, excluding common preambles."""
    ignored = {
        "my", "mobile", "phone", "number", "is", "the", "hai", "hain",
        "mera", "मेरे", "मेरा", "फोन", "नंबर", "नम्बर", "है", "हैं",
        "uh", "um", "and", "plus", "और", "तथा",
    }
    tokens = (
        token.strip("()[]{}\"'")
        for token in re.split(r"[\s,.!?।॥:;\-–—]+", str(text or "").casefold())
    )
    return sum(
        bool(token)
        and not token.isdecimal()
        and token not in _PHONE_DIGIT_WORDS
        and token not in ignored
        for token in tokens
    )


def _phone_rescue_is_better(primary: str, english: str) -> bool:
    """Prefer a plausible longer phone decode, or a cleaner equal-length one."""
    primary_digits = _phone_digit_count(primary)
    candidate_digits = _phone_digit_count(english)
    candidate_plausible = 3 <= candidate_digits <= 15
    primary_plausible = 3 <= primary_digits <= 15
    # Treat an overlong primary as unusable (score 0), but never select an
    # overlong alternate. This keeps the chosen transcript bounded while
    # allowing a valid 10-digit alternate to replace a runaway hallucination.
    primary_score = primary_digits if primary_plausible else 0
    if candidate_plausible and candidate_digits > primary_score:
        return True
    # If both decode the same number of explicit digits, prefer the candidate
    # only when it contains fewer unknown words. Do not sacrifice recognized
    # digits for a cleaner but shorter transcript, and never infer unknown words.
    return (
        candidate_plausible
        and candidate_digits == primary_digits
        and _phone_unknown_token_count(english) < _phone_unknown_token_count(primary)
    )


def _phone_rescue_language(
    primary_language: str,
    fallback_language: str,
    *,
    installed: set[str],
    resident: set[str],
) -> str | None:
    """Choose only an already-resident Hindi/English phone rescue decoder.

    Phone dictation is commonly code-switched and the utterance-level LID can
    select a regional decoder (for example Punjabi) even though the caller's
    established conversation language is Hindi. In that case, try that
    established decoder as a candidate, but never load a model on the call path.
    """
    primary = str(primary_language or "").lower().split("-", 1)[0]
    fallback = str(fallback_language or "").lower().split("-", 1)[0]
    if primary in {"hi", "en"}:
        candidate = "en" if primary == "hi" else "hi"
    elif fallback in {"hi", "en"} and fallback != primary:
        candidate = fallback
    else:
        return None
    return candidate if candidate in installed and candidate in resident else None

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
                # Use the same bounded CPU budget as the primary LID
                # session. The English rescue runs after the primary
                # detector, so a second thread can reduce auto-detection
                # wall time without running two inference models at once.
                num_threads=LID_THREADS,
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
    # Preserve the actual 23-class LID result. Filtering the argmax here would
    # relabel a confidently detected but disabled language (for example Urdu)
    # as Hindi and feed the wrong transcript to the workflow.
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
    allowed_languages: set[str] | frozenset[str] | None = None,
) -> tuple[str, str]:
    """Choose an installed decoder without silently relabeling clear speech."""
    detected = str(detected or "").lower().replace("_", "-").split("-", 1)[0]
    fallback = str(fallback_language or "").lower().replace("_", "-").split("-", 1)[0]
    enabled = installed & AUTO_DETECT_LANGUAGES - {"ur"}
    if allowed_languages is not None:
        enabled &= {
            str(code).strip().lower().replace("_", "-").split("-", 1)[0]
            for code in allowed_languages
            if isinstance(code, str) and str(code).strip()
        }
    # Urdu has no configured reply voice in this product. Use the Hindi
    # decoder only when the active TTS model explicitly enables Hindi.
    if detected == "ur" and "hi" in enabled:
        return "hi", "urdu_routed_to_hindi"
    supported = enabled
    if detected not in supported:
        threshold = AUTO_ENGLISH_MIN_CONFIDENCE if detected == "en" else AUTO_LANGUAGE_MIN_CONFIDENCE
        if detected in LID_LANGUAGE_CODES and fallback in supported:
            return fallback, "unsupported_language_held_previous"
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
    allowed_languages: str | None = Form(None),
) -> dict:
    if model != MODEL_ID:
        raise HTTPException(status_code=404, detail="Unknown local STT model")
    requested_language = (language or "auto").strip().lower().replace("_", "-").split("-", 1)[0]
    auto_detect = requested_language in {"", "auto", "multi", "default", "unknown"}
    installed = _installed_languages()
    enabled_languages = None
    if allowed_languages is not None:
        enabled_languages = {
            code.strip().lower().replace("_", "-").split("-", 1)[0]
            for code in allowed_languages.split(",")
            if code.strip()
        } & (AUTO_DETECT_LANGUAGES - {"ur"})
        enabled_languages &= set(installed)
        if auto_detect and not enabled_languages:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "no_enabled_tts_languages",
                    "message": "The selected voice has no installed language enabled for automatic speech routing.",
                },
            )
    if auto_detect and _lid_session is None:
        raise HTTPException(status_code=503, detail="Local automatic language detection is unavailable")
    lang = requested_language
    fallback = (fallback_language or "").strip().lower().replace("_", "-").split("-", 1)[0]
    available_auto_languages = set(installed) & AUTO_DETECT_LANGUAGES
    if enabled_languages is not None:
        available_auto_languages &= enabled_languages
    if fallback not in available_auto_languages:
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
                detected_language,
                language_confidence,
                fallback or None,
                set(installed),
                detection_route,
                enabled_languages,
            )
            if lang not in installed:
                raise HTTPException(status_code=503, detail="Selected STT language is not installed on this engine")
        lid_ms = round((time.monotonic() - lid_started) * 1000) if auto_detect else 0
        audio_ms = round(len(waveform) * 1000 / sample_rate)
        decoder_was_resident = lang in _loaded
        decode_started = time.monotonic()
        text = await asyncio.to_thread(decode, lang)
        phone_rescue_language = _phone_rescue_language(
            lang,
            fallback,
            installed=available_auto_languages,
            resident=set(_loaded),
        ) if phone_capture else None
        if (
            phone_capture
            and phone_rescue_language
            # Keep the normal phone-slot path to one decode. Running both
            # recognizers for every phone utterance serializes two CPU-heavy
            # inference passes under _inference_lock and made routine turns
            # needlessly slow. The alternate decoder is a rescue only when
            # the primary contains an explicit phone preamble, a plausible
            # multi-digit fragment with unknown words, or an implausible
            # runaway. Do not reinterpret arbitrary speech as a number just
            # because the previous turn requested a phone number.
            and _should_try_phone_rescue(text)
        ):
            # Phone strings are commonly spoken in English inside Hindi calls,
            # and LID can route an English digit utterance to Moonshine. Try
            # the other warm decoder only when the first result cannot be used;
            # reject overlong hallucinations instead of carrying fake digits.
            other_language = phone_rescue_language
            other_text = await asyncio.to_thread(decode, other_language)
            if _phone_rescue_is_better(text, other_text):
                text = other_text
                language_route = f"phone_{other_language}_rescue"
        decode_ms = round((time.monotonic() - decode_started) * 1000)
    duration_ms = round((time.monotonic() - started) * 1000)
    _logger.info(
        "indic_stt_request_trace auto=%s language=%s route=%s audio_ms=%s "
        "decoder_was_resident=%s queue_ms=%s lid_ms=%s decode_ms=%s duration_ms=%s",
        auto_detect,
        lang,
        language_route,
        audio_ms,
        decoder_was_resident,
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
