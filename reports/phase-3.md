# Phase 3: Local Engines (Whisper, Piper, Ollama) — Completion Report

**Date**: 2026-10-05  
**Branch**: `stabilize`  
**Status**: PASSED (All WP3 Requirements Met)

---

## 1. Summary of Changes

Phase 3 implements self-hosted CPU local engine isolation, management, and verification across Faster-Whisper STT (Speaches), Piper Neural TTS, and Ollama LLM. The server is protected against memory starvation, local engines are gated behind the Docker Compose `local` profile, and the admin panel features real inspection, download, delete, and audio test capabilities.

### 1.1 Local Engines Docker Architecture & Resource Floors
- **Docker Compose Profiles**:
  - Gated `ollama`, `piper`, and `whisper` behind `profiles: ["local"]` in both `docker-compose.yaml` and `docker-compose.aapanel.yaml`.
  - Unless `ENABLE_LOCAL_AI_ENGINE=true`, local engine containers do NOT start on `docker compose up`, saving ~3.5–5 GB RAM for host websites.
- **Resource Floors & Default Limits** (per Part 6 specification):
  - **Piper TTS**: Limit `768M` RAM, reservation `512M` RAM, 1.0 CPU.
  - **Faster-Whisper (Speaches)**: Limit `1536M` RAM, reservation `768M` RAM, 2.0 CPU. Replaced legacy `WHISPER_MODEL` with Speaches standard `PRELOAD_MODELS=Systran/faster-whisper-tiny`.
  - **Ollama LLM**: Limit `4096M` RAM, reservation `2048M` RAM, 2.0 CPU.
- **Healthchecks**:
  - Piper: `curl -f http://localhost:5000/voices`
  - Speaches Whisper: `curl -f http://localhost:8000/health`
  - Ollama: `curl -f http://localhost:11434/api/tags`
- **Deploy Script Hardening (`deploy.sh`)**:
  - Automatically reads `ENABLE_LOCAL_AI_ENGINE` and passes `--profile local` to Docker Compose when true.
  - Automatically stops local engine containers when `ENABLE_LOCAL_AI_ENGINE=false` to free host RAM.
  - Performs an automated safety database backup (`pg_dump`) before running Alembic migrations.

### 1.2 Piper Neural TTS Voice Manager & Resampling
- **Curated Indic & Global Catalog**: Added `GET /api/v1/admin/settings/piper/all-voices` with metadata for Hindi (`hi_IN-priyamvada-medium`, `hi_IN-pratham-medium`), Telugu (`te_IN-rama-medium`), Malayalam (`ml_IN-ananya-medium`), Marathi, Tamil, Bengali, Nepali, and English. Supports language query filtering (`?language=hi`).
- **Live Voice Synthesis Verification**: Added `POST /api/v1/admin/settings/piper/test` which queries `/synthesize`, checks audio length and sample rate, and returns base64 audio for instant browser testing.
- **Voice Deletion**: Added `DELETE /api/v1/admin/settings/piper/voices/{voice_id}`.
- **Audio Resampling**: Confirmed Pipecat `PiperHttpTTSService` and `TTSService._stream_audio_frames_from_iterator` auto-detect Piper's 22.05 kHz output and resample to `transport_out_sample_rate` (8 kHz for telephony, 16 kHz / 24 kHz for WebRTC).

### 1.3 Faster-Whisper (Speaches) STT Manager
- **Model Inspection**: Enhanced `GET /api/v1/admin/settings/whisper/models` to query Speaches `/models` and report real installed state for `tiny`, `base`, and `small`.
- **Model Download & Unload**: Added `POST /api/v1/admin/settings/whisper/download` and `DELETE /api/v1/admin/settings/whisper/models/{model_id}`.
- **Live STT Verification**: Added `POST /api/v1/admin/settings/whisper/test` which transcribes bundled audio fixtures (`tests/fixtures/audio/hi_sample.wav` and `en_sample.wav`) and returns transcription text, latency, and status.

### 1.4 Ollama Tool-Calling Test
- Added `POST /api/v1/admin/settings/ollama/test` which sends a test prompt with a structured function-calling schema to Ollama `/api/chat` to verify if the model supports tool calls before allowing complex agent workflows.

### 1.5 Admin Settings UI Modernization
- Added complete Faster-Whisper STT Manager card to `ui/src/app/admin/settings/page.tsx` with live status, model download selector, STT audio verification runner, and model list.
- Added "Test Tools" verification button on Ollama models.
- Added voice deletion and base64 audio playback to Piper voices table.
- Added client methods to `ui/src/lib/kodewavesApi.ts`.

---

## 2. Test Verification Matrix

| Check | Expected | Result | Notes |
|---|---|---|---|
| Docker Compose Profiles | `profiles: ["local"]` on ollama, piper, whisper | PASS | Present in root and aaPanel compose |
| Memory Limits & Floors | Piper 768M/512M, Whisper 1.5G/768M, Ollama 4G | PASS | Part 6 compliance verified |
| Deploy Script Logic | Detects `ENABLE_LOCAL_AI_ENGINE` & runs `pg_dump` | PASS | Verified in `deploy.sh` |
| Piper All Voices API | Returns curated catalog with Hindi and English voices | PASS | Tested with and without language filter |
| Whisper Models API | Returns model tiers with installed/available status | PASS | Gracefully handles engine offline |
| Combined Regression | All Phase 1, Phase 2, and Phase 3 tests pass | PASS | 12 of 12 tests passed |

---

## 3. Automated Test Suite Output

```
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
collected 12 items

api\tests\test_truth_layer_catalog.py::test_normalize_provider_name PASSED
api\tests\test_truth_layer_catalog.py::test_catalog_visibility_no_keys_empty_manifest PASSED
api\tests\test_truth_layer_catalog.py::test_catalog_visibility_with_google_key PASSED
api\tests\test_provider_matrix_and_layers.py::test_alias_normalization_comprehensive PASSED
api\tests\test_provider_matrix_and_layers.py::test_gemini_models_updated PASSED
api\tests\test_provider_matrix_and_layers.py::test_krutrim_removed PASSED
api\tests\test_provider_matrix_and_layers.py::test_disabled_key_does_not_fallback_to_env PASSED
api\tests\test_provider_matrix_and_layers.py::test_deepgram_language_handling PASSED
api\tests\test_local_engines_manager.py::test_docker_compose_local_profiles_and_limits PASSED
api\tests\test_local_engines_manager.py::test_piper_all_voices_endpoint PASSED
api\tests\test_local_engines_manager.py::test_whisper_models_endpoint PASSED
api\tests\test_local_engines_manager.py::test_deploy_script_profile_handling PASSED

============================= 12 passed in 9.17s ==============================
```
