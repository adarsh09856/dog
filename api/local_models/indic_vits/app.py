"""Local AI4Bharat VITS Rasa & Piper multilingual speech engine for Indian languages and English."""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
import re
import threading
import unicodedata
import wave
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
try:
    import sherpa_onnx
except ImportError:
    sherpa_onnx = None
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response, StreamingResponse
from huggingface_hub import hf_hub_download
from pydantic import BaseModel, Field

MODEL_ID = "indic-vits-rasa-13"
MODEL_REPO = "MatiasLin/sherpa-onnx-vits-rasa-13"
MODEL_REVISION = "b5afd4e991e3bdd6195528de650e2ed219d47506"
MODEL_DIR = Path(os.environ.get("INDIC_VITS_MODEL_DIR", "/models/indic-vits-rasa-13"))
PIPER_DIR = Path(os.environ.get("PIPER_MODEL_DIR", "/models/piper"))
MELO_DIR = Path(os.environ.get("MELO_ENGLISH_MODEL_DIR", "/models/melo-english"))
MELO_REPO = "M5Stack/MeloTTS-English-axmodel"
MELO_REVISION = "815731592c5c050da9505fa4b7f16aee74fb06a8"
MELO_FILES = {
    "model.onnx": "ef9bae119d763c9d05e9271a864de048d49c86c41fdc2b4d15a5bab39c31f78f",
    "tokens.txt": "96026b19956133d23b7048c0e75466d061f31dea4e848315689259876b531376",
    "lexicon.txt": "d9180223df27dc6addafbcc2a4236388ebd170d22df89ac7008a24448d37906b",
}
THREADS = max(1, int(os.environ.get("INDIC_VITS_THREADS", "2")))
SAMPLE_RATE = 24_000

# Trained speaker slots for AI4Bharat VITS Rasa 13 regional languages
RASA_SPEAKERS: dict[str, tuple[int, str, str, str]] = {
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

# Native Hindi and Urdu voices. English is served by Melo's EN_INDIA speaker.
PIPER_SPEAKERS: dict[str, tuple[str, str, str, str, str]] = {
    "HIN_M": ("hi", "Hindi", "male", "vits-piper-hi_IN-pratham-medium", "hi_IN-pratham-medium.onnx"),
    "HIN_F": ("hi", "Hindi", "female", "vits-piper-hi_IN-priyamvada-medium", "hi_IN-priyamvada-medium.onnx"),
    "URD_M": ("ur", "Urdu", "male", "vits-piper-ur_PK-fasih-medium", "ur_PK-fasih-medium.onnx"),
}

# Static catalog definition
ALL_SPEAKER_SPECS: dict[str, tuple[int | None, str, str, str]] = {
    **RASA_SPEAKERS,
    **{k: (None, v[0], v[1], v[2]) for k, v in PIPER_SPEAKERS.items()},
    # Upstream identifies this accent, but does not document speaker gender.
    "ENG_IN": (2, "en", "Indian English", "unspecified"),
}

# Backward compatibility alias
SPEAKERS = ALL_SPEAKER_SPECS

# Script classification
SCRIPT_TO_LANGUAGE = (
    (0x0A00, 0x0A7F, "pa"),   # Gurmukhi -> Punjabi
    (0x0B80, 0x0BFF, "ta"),   # Tamil -> Tamil
    (0x0C00, 0x0C7F, "te"),   # Telugu -> Telugu
    (0x0C80, 0x0CFF, "kn"),   # Kannada -> Kannada
    (0x0D00, 0x0D7F, "ml"),   # Malayalam -> Malayalam
    (0x0600, 0x06FF, "ur"),   # Perso-Arabic -> Urdu
)

DEVANAGARI_LANGUAGES = {"hi", "mr", "ne", "sa", "mai", "brx", "doi"}
BENGALI_ASSAMESE_LANGUAGES = {"bn", "as"}

PREVIEWS = {
    "as": "নমস্কাৰ, মই আপোনাক কেনেকৈ সহায় কৰিব পাৰোঁ",
    "bn": "নমস্কার, আমি আপনাকে কীভাবে সাহায্য করতে পারি",
    "brx": "रावजों, आं नोंखौ माबोरै मदद होनो हायो",
    "doi": "नमस्कार, तुसेंगी केह् मदद चाहिदी ऐ",
    "en": "Hello, how can I assist you today",
    "hi": "नमस्ते, बताइए, मैं आपकी कैसे मदद करूँ",
    "kn": "ನಮಸ್ಕಾರ, ನಿಮಗೆ ಯಾವ ಸಹಾಯ ಬೇಕು",
    "mai": "नमस्कार, अहाँ केहन सहायता चाहैत छी",
    "ml": "നമസ്കാരം, നിങ്ങൾക്ക് എന്ത് സഹായമാണ് വേണ്ടത്",
    "mr": "नमस्कार, तुम्हाला कोणत्या मदतीची गरज आहे",
    "ne": "नमस्कार, तपाईंलाई कस्तो सहयोग चाहिएको छ",
    "pa": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਤੁਹਾਨੂੰ ਕਿਸ ਚੀਜ਼ ਵਿੱਚ ਮਦਦ ਚਾਹੀਦੀ ਹੈ",
    "sa": "नमस्कारः, भवते किम् साहाय्यम् अपेक्षितम्",
    "ta": "வணக்கம், உங்களுக்கு என்ன உதவி வேண்டும்",
    "te": "నమస్కారం, మీకు ఏ సహాయం కావాలి",
    "ur": "السلام علیکم، بتائیے، آپ کو کس مدد کی ضرورت ہے",
}

RASA_MODEL: sherpa_onnx.OfflineTts | None = None
PIPER_MODELS: dict[str, sherpa_onnx.OfflineTts] = {}
MELO_MODEL: sherpa_onnx.OfflineTts | None = None
WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="indic-vits")
LOCK = asyncio.Lock()


def get_active_speakers() -> dict[str, tuple[int | None, str, str, str]]:
    """Return only voices whose underlying models are loaded and ready."""
    active: dict[str, tuple[int | None, str, str, str]] = {}
    if RASA_MODEL is not None:
        active.update(RASA_SPEAKERS)
    for voice_id, model in PIPER_MODELS.items():
        if voice_id in PIPER_SPEAKERS and model is not None:
            spec = PIPER_SPEAKERS[voice_id]
            active[voice_id] = (None, spec[0], spec[1], spec[2])
    if MELO_MODEL is not None:
        active["ENG_IN"] = ALL_SPEAKER_SPECS["ENG_IN"]
    return active


def voice_for_text(text: str, preferred_voice: str, context_language: str | None = None) -> str:
    """Use matching installed voice for unambiguous regional script, or preserve
    verified language context for shared scripts (Devanagari, Bengali-Assamese).

    1. Unambiguous scripts (kn, ta, te, ml, pa, ur) map directly to their language.
    2. Shared scripts (Devanagari, Bengali-Assamese) check preferred_voice and context_language:
       - Assamese preferred voice (ASM_F, ASM_M) is PRESERVED on Bengali-Assamese script.
       - Marathi context with KAN_M voice routes to Marathi (MAR_M), NOT Hindi.
       - Hindi context with MAR_M voice routes to Hindi (HIN_M), NOT Marathi.
    3. Respects speaker gender when switching voices within the target language.
    """
    active_speakers = get_active_speakers()
    if preferred_voice not in active_speakers:
        raise ValueError("Selected voice is not loaded")

    pref_info = active_speakers[preferred_voice]
    pref_lang = pref_info[1]
    pref_gender = pref_info[3]

    # Count script characters
    counts: dict[str, int] = {}
    for character in text:
        code = ord(character)
        matched_unambiguous = False
        for start, end, lang in SCRIPT_TO_LANGUAGE:
            if start <= code <= end:
                counts[lang] = counts.get(lang, 0) + 1
                matched_unambiguous = True
                break
        if matched_unambiguous:
            continue

        if 0x0980 <= code <= 0x09FF:
            counts["bn_as"] = counts.get("bn_as", 0) + 1
        elif 0x0900 <= code <= 0x097F:
            counts["deva"] = counts.get("deva", 0) + 1
        elif (0x0041 <= code <= 0x005A) or (0x0061 <= code <= 0x007A):
            counts["en"] = counts.get("en", 0) + 1

    if not counts and any(unicodedata.category(c).startswith("L") for c in text):
        raise ValueError("No loaded voice supports this text script")
    if not counts:
        return preferred_voice

    dominant = max(counts, key=counts.get)

    target_lang = None
    if dominant in ("pa", "ta", "te", "kn", "ml", "ur", "en"):
        target_lang = dominant
    elif dominant == "bn_as":
        clean_ctx = (context_language or "").lower().replace("_", "-").split("-", 1)[0]
        if clean_ctx in {"as", "bn"}:
            target_lang = clean_ctx
        elif pref_lang in {"as", "bn"}:
            target_lang = pref_lang
        else:
            raise ValueError("Select Assamese or Bengali for this shared-script text")
    elif dominant == "deva":
        clean_ctx = (context_language or "").lower().replace("_", "-").split("-", 1)[0]
        if clean_ctx in DEVANAGARI_LANGUAGES:
            target_lang = clean_ctx
        elif pref_lang in DEVANAGARI_LANGUAGES:
            target_lang = pref_lang
        else:
            raise ValueError("Select the spoken language for this Devanagari text")

    if not target_lang:
        return preferred_voice

    if pref_lang == target_lang:
        return preferred_voice

    candidates = [v for v, (_, l, _, _) in active_speakers.items() if l == target_lang]
    if not candidates:
        raise ValueError(f"No loaded voice supports language '{target_lang}'")

    if pref_gender == "unspecified":
        return candidates[0]
    gender_matched = [v for v in candidates if active_speakers[v][3] == pref_gender]
    # A single upstream voice with undocumented gender remains available to
    # either preference; the catalog explicitly reports this limitation.
    if not gender_matched:
        gender_matched = [v for v in candidates if active_speakers[v][3] == "unspecified"]
    if not gender_matched:
        raise ValueError(f"No loaded {pref_gender} voice supports language '{target_lang}'")
    return gender_matched[0]


def speech_segments(text: str, preferred_voice: str, context_language: str | None = None):
    """Route script changes inside one reply, retaining numbers and punctuation.

    Shared scripts still need verified language context. This is text routing,
    not spoken-language identification or translation.
    """
    segments: list[tuple[str, str]] = []
    for match in re.finditer(r"\S+\s*", text):
        part = match.group()
        has_letters = any(unicodedata.category(c).startswith("L") for c in part)
        voice = voice_for_text(part, preferred_voice, context_language) if has_letters else (
            segments[-1][0] if segments else preferred_voice
        )
        # Bound native inference memory for long punctuation-free replies.
        # Keep complete words; the callbacks still stream each bounded phrase.
        if segments and segments[-1][0] == voice and len(segments[-1][1]) + len(part) <= 120:
            segments[-1] = (voice, segments[-1][1] + part)
        else:
            segments.append((voice, part))
    return segments


def _pcm(samples) -> bytes:
    samples = np.asarray(samples, dtype=np.float32)
    if not samples.size or not np.isfinite(samples).all():
        raise RuntimeError("Local voice returned invalid audio")
    return (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()


def _resample(samples: np.ndarray | list[float], in_rate: int, out_rate: int) -> np.ndarray:
    """Fast linear audio resampling in numpy."""
    arr = np.asarray(samples, dtype=np.float32)
    if in_rate == out_rate or len(arr) == 0:
        return arr
    num_samples = int(len(arr) * out_rate / in_rate)
    return np.interp(
        np.linspace(0, len(arr), num_samples, endpoint=False),
        np.arange(len(arr)),
        arr,
    ).astype(np.float32)


def _generate(text: str, voice: str, speed: float, callback=None, context_language: str | None = None) -> bytes:
    text = unicodedata.normalize("NFC", text).strip().rstrip(".!?।॥ \n")
    if not text:
        raise ValueError("Speech text must contain words")
    segments = speech_segments(text, voice, context_language)
    cancelled = False
    def forward(samples, progress):
        nonlocal cancelled
        result = callback(samples, progress)
        cancelled = result == 0
        return result
    chunks = []
    for effective_voice, part in segments:
        if cancelled:
            break
        chunks.append(_generate_one(part.strip(), effective_voice, speed,
                                    forward if callback else None))
    return b"".join(chunks)


def _generate_one(text: str, effective_voice: str, speed: float, callback=None) -> bytes:
    if effective_voice == "ENG_IN":
        if MELO_MODEL is None:
            raise RuntimeError("Indian English voice is loading")
        def on_audio(samples, progress):
            return callback(_resample(samples, MELO_MODEL.sample_rate, SAMPLE_RATE), progress)
        audio = MELO_MODEL.generate(text, sid=2, speed=speed, callback=on_audio) if callback else (
            MELO_MODEL.generate(text, sid=2, speed=speed))
        return _pcm(_resample(audio.samples, audio.sample_rate, SAMPLE_RATE))

    if effective_voice in PIPER_SPEAKERS:
        model = PIPER_MODELS.get(effective_voice)
        if model is None:
            raise RuntimeError(f"Local voice {effective_voice} is not loaded")
        in_rate = model.sample_rate

        if callback:
            def piper_cb(samples, progress):
                resampled = _resample(samples, in_rate, SAMPLE_RATE)
                return callback(resampled, progress)
            audio = model.generate(text, speed=speed, callback=piper_cb)
        else:
            audio = model.generate(text, speed=speed)

        resampled = _resample(audio.samples, in_rate, SAMPLE_RATE)
        return _pcm(resampled)
    else:
        if RASA_MODEL is None:
            raise RuntimeError("Regional voice model is loading")
        config = sherpa_onnx.GenerationConfig()
        config.sid = RASA_SPEAKERS[effective_voice][0]
        config.speed = speed
        config.extra = {"emotion_id": "4"}

        audio = RASA_MODEL.generate(text, config, callback) if callback else RASA_MODEL.generate(text, config)
        if audio.sample_rate != SAMPLE_RATE:
            raise RuntimeError("Local voice returned invalid audio")
        return _pcm(audio.samples)


async def stream_pcm(request, context_language: str | None = None):
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
        return 1

    async with LOCK:
        future = loop.run_in_executor(
            WORKER, _generate, request.input, request.voice, request.speed, callback, context_language)
        future.add_done_callback(lambda _: queue.put_nowait(None))
        try:
            while (chunk := await queue.get()) is not None:
                yield chunk
            pcm = await asyncio.shield(future)
            if not emitted:
                yield pcm
        finally:
            stopped.set()
            if not future.done():
                await asyncio.shield(future)


def _load() -> None:
    global RASA_MODEL, PIPER_MODELS, MELO_MODEL
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for filename in ("model.onnx", "tokens.txt"):
        if not (MODEL_DIR / filename).is_file():
            hf_hub_download(MODEL_REPO, filename, revision=MODEL_REVISION, local_dir=MODEL_DIR)
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(MODEL_DIR / "model.onnx"), tokens=str(MODEL_DIR / "tokens.txt")),
            num_threads=THREADS, provider="cpu"), max_num_sentences=1)
    RASA_MODEL = sherpa_onnx.OfflineTts(config)

    for voice_id, (_, _, _, folder, onnx_file) in PIPER_SPEAKERS.items():
        model_path = PIPER_DIR / folder / onnx_file
        tokens_path = PIPER_DIR / folder / "tokens.txt"
        data_dir = PIPER_DIR / folder / "espeak-ng-data"
        if model_path.is_file() and tokens_path.is_file() and data_dir.is_dir():
            piper_cfg = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=str(model_path),
                        tokens=str(tokens_path),
                        data_dir=str(data_dir),
                    ),
                    num_threads=THREADS,
                    provider="cpu",
                )
            )
            PIPER_MODELS[voice_id] = sherpa_onnx.OfflineTts(piper_cfg)

    MELO_DIR.mkdir(parents=True, exist_ok=True)
    for filename, expected_hash in MELO_FILES.items():
        path = MELO_DIR / filename
        if not path.is_file():
            hf_hub_download(MELO_REPO, filename, revision=MELO_REVISION, local_dir=MELO_DIR)
        with path.open("rb") as model_file:
            if hashlib.file_digest(model_file, "sha256").hexdigest() != expected_hash:
                raise RuntimeError(f"Indian English model checksum mismatch: {filename}")
    MELO_MODEL = sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(MELO_DIR / "model.onnx"), tokens=str(MELO_DIR / "tokens.txt"),
                lexicon=str(MELO_DIR / "lexicon.txt")),
            num_threads=THREADS, provider="cpu"), max_num_sentences=1))
    if MELO_MODEL.num_speakers != 5 or MELO_MODEL.sample_rate != 44100:
        raise RuntimeError("Unexpected Indian English model speaker inventory")

    # Warmup
    _generate(PREVIEWS["ta"], "TAM_F", 1.0)
    if "HIN_M" in PIPER_MODELS:
        _generate(PREVIEWS["hi"], "HIN_M", 1.0)
    _generate(PREVIEWS["en"], "ENG_IN", 1.0)


@asynccontextmanager
async def lifespan(_app):
    await asyncio.get_running_loop().run_in_executor(WORKER, _load)
    yield


app = FastAPI(title="Kodewaves Multilingual Indian CPU Speech", lifespan=lifespan)


class SpeechRequest(BaseModel):
    model: str = MODEL_ID
    voice: str
    input: str = Field(min_length=1, max_length=600)
    response_format: str = "pcm"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str | None = None  # Context language (e.g. "hi", "mr", "as")


@app.get("/health")
async def health():
    if RASA_MODEL is None and not PIPER_MODELS:
        raise HTTPException(503, "Regional voice engine is loading")
    return {"status": "ok", "loaded_piper_voices": list(PIPER_MODELS.keys()),
            "indian_english_loaded": MELO_MODEL is not None}


@app.get("/v1/models")
async def models():
    active_speakers = get_active_speakers()
    active_languages = sorted({
        f"{speaker[1]}-IN" for speaker in active_speakers.values() if speaker[1] not in ("en", "ur")
    } | ({"en-IN"} if any(s[1] == "en" for s in active_speakers.values()) else set())
      | ({"ur-IN", "ur-PK"} if any(s[1] == "ur" for s in active_speakers.values()) else set()))

    return {"object": "list", "data": [{
        "id": MODEL_ID,
        "name": "Kodewaves Regional + Hindi + Indian English (CPU)",
        "task": "text-to-speech",
        "installed": bool(active_speakers),
        "streaming": True,
        "streaming_granularity": "sentence",
        "sample_rate": SAMPLE_RATE,
        "languages": active_languages,
        "automatic_voice_routing": "reply-script-with-language-context",
        "gender_limitations": {"ENG_IN": "One Indian-English speaker; gender not documented by upstream"},
        "attribution": "AI4Bharat VITS Rasa, CC BY 4.0; Piper VITS and MeloTTS, MIT License",
        "voices": [{
            "id": voice,
            "name": f"{name} — {gender.title()}" if gender != "unspecified" else name,
            "gender": gender,
            "accent": "Indian English" if lang == "en" else ("Urdu" if lang == "ur" else f"Indian {name}"),
            "languages": ["en-IN"] if lang == "en" else ([f"{lang}-IN"] + (["ur-PK"] if lang == "ur" else [])),
            "preview_text": PREVIEWS.get(lang, "")
        } for voice, (_sid, lang, name, gender) in active_speakers.items()],
    }]}


@app.post("/v1/audio/speech")
async def speech(
    request: SpeechRequest,
    language_hint: str | None = Header(default=None, alias="X-Kodewaves-Speech-Language"),
):
    if request.model != MODEL_ID:
        raise HTTPException(404, "Unknown local TTS model")

    active_speakers = get_active_speakers()
    if request.voice not in active_speakers:
        raise HTTPException(
            400,
            f"Voice '{request.voice}' is not currently loaded or available. Available voices: {', '.join(sorted(active_speakers))}"
        )

    if request.response_format not in {"pcm", "wav"}:
        raise HTTPException(400, "Supported formats: pcm, wav")

    clean_text = unicodedata.normalize("NFC", request.input).strip().rstrip(".!?।॥ \n")
    if not clean_text:
        raise HTTPException(400, "Speech text must contain words")

    context_language = request.language or (language_hint if isinstance(language_hint, str) else None)
    try:
        speech_segments(clean_text, request.voice, context_language)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if request.response_format == "pcm":
        return StreamingResponse(stream_pcm(request, context_language), media_type="audio/pcm")

    async with LOCK:
        future = asyncio.get_running_loop().run_in_executor(
            WORKER, _generate, request.input, request.voice, request.speed, None, context_language)
        try:
            pcm = await asyncio.shield(future)
        except asyncio.CancelledError:
            await future
            raise

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    return Response(buffer.getvalue(), media_type="audio/wav")
