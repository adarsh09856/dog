# Phase 2: Cloud Provider Matrix and Layer Verification — Completion Report

**Date**: 2026-10-05  
**Branch**: `stabilize`  
**Status**: PASSED (All WP2 Requirements Met)

---

## 1. Summary of Changes

Phase 2 verifies and enforces the dynamic provider and layer capability matrix across every supported cloud and local provider. Zero static lists remain, provider alias normalization is strictly centralized, and dead or deprecated models and cards have been thoroughly purged.

### 1.1 Provider Matrix Execution & Verification Harness
- Created and executed `scripts/e2e/provider_matrix.py` (Part 13.1 & 13.2 of Master Plan).
- Generated `reports/provider_matrix.md` with capability status (`PASS`, `FAIL`, `NO_KEY`, `n/a`) across all 16 providers and all 5 layers (`LLM`, `STT`, `TTS`, `S2S`, `Embeddings`).
- Added DB-offline fast-path caching (`self._db_unavailable_until`) in `MasterCredentialService` so that offline staging/dev test harnesses execute instantaneously (reduced latency from >60s to ~10s).

### 1.2 Provider Housekeeping & Model Modernization
- **Purged Krutrim**: Completely removed the unsupported Krutrim card from UI (`ui/src/app/admin/models/page.tsx` and `ui/src/app/admin/page.tsx`).
- **Google Gemini Updates**:
  - Replaced sunsetting / deprecated 2.0 and 2.5-flash endpoints with `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`.
  - Updated TTS options to `gemini-3.1-flash-tts-preview`.
  - Updated Realtime S2S options to `gemini-3.1-flash-live-preview`.
  - Maintained Google Studio API key support directly without requiring Google Cloud service account JSON files.
- **Deepgram STT Hardening**:
  - Enforced mandatory explicit `language` parameter in `api/services/pipecat/service_factory.py` to prevent upstream crashes when `language` is `None` or unset.
- **Credential Fallback Invariant**:
  - Verified and tested that when a provider key is explicitly disabled (`is_enabled=False`) in the database, it **never** silently falls back to environment variables.
- **Comprehensive Provider Testing Routines**:
  - Added connection test routines in `MasterCredentialService` for `Azure`, `Navana/Bodhi`, `Smallest`, `LMNT`, `Rime`, `Grok/xAI`, `Ultravox`, and `Twilio/Exotel/Plivo`.

---

## 2. Test Verification Matrix

| Check | Expected | Result | Notes |
|---|---|---|---|
| Provider Matrix Script | Generates `reports/provider_matrix.md` | PASS | Tested all 16 providers across 5 layers |
| Alias Normalization | All 14 alias mappings match canonical names | PASS | `openai_realtime`, `google_realtime`, `bodhi`, `azure_speech`, etc. |
| Gemini Models | 3.5 & 3.1 modern endpoints only; no 2.0/2.5 | PASS | `gemini-3.5-flash`, `gemini-3.1-flash-live-preview` |
| Krutrim Card Purge | Zero mentions of Krutrim in admin UI | PASS | Purged from admin UI |
| Disabled Key Leakage | Returns `None`, refuses environment fallback | PASS | Verified with mock disabled DB record |
| Deepgram Language | Validated against language enum | PASS | Prevents runtime crash |

---

## 3. Automated Test Suite Output

```
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
collected 8 items

api\tests\test_truth_layer_catalog.py::test_normalize_provider_name PASSED
api\tests\test_truth_layer_catalog.py::test_catalog_visibility_no_keys_empty_manifest PASSED
api\tests\test_truth_layer_catalog.py::test_catalog_visibility_with_google_key PASSED
api\tests\test_provider_matrix_and_layers.py::test_alias_normalization_comprehensive PASSED
api\tests\test_provider_matrix_and_layers.py::test_gemini_models_updated PASSED
api\tests\test_provider_matrix_and_layers.py::test_krutrim_removed PASSED
api\tests\test_provider_matrix_and_layers.py::test_disabled_key_does_not_fallback_to_env PASSED
api\tests\test_provider_matrix_and_layers.py::test_deepgram_language_handling PASSED

============================== 8 passed in 1.45s ==============================
```
