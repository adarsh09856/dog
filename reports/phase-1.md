# Phase 1: Truth Layer and Database — Completion Report

**Date**: 2026-10-05  
**Branch**: `stabilize`  
**Status**: PASSED (All Exit Tests Met)

---

## 1. Summary of Changes

Phase 1 establishes the **Database Truth Layer** as the sole source of capability manifests across Kodewaves. The core invariant — *"Key in Admin → Live Capability Verification → Dynamic User Catalog"* — is now fully wired with zero static fallback lists in the catalog endpoint or UI voice selector.

### 1.1 Database Schema & Migration
- Created migration: `api/alembic/versions/b2c3d4e5f6a7_add_truth_layer_catalog_tables.py`
  - Down revision: `f4b18c7d9a01` (Single head maintained: exactly 1 head).
  - Extended `ai_model_catalog`: Added `layer` (`llm`, `stt`, `tts`, `s2s`, `embeddings`), `enabled`, `recommended`, `is_default`, `source`, `status` (`PASS`, `FAIL`, `UNTESTED`, `UNAVAILABLE`), `latency_ms`, `last_verified_at`, `last_error`, `languages`, `supports_tools`, `supports_streaming`, `wholesale_cost`, `markup_percent`.
  - Extended `platform_master_credentials`: Added `extra_config` JSON and `last_status`.
  - Created `voice_catalog`: Holds voice options per provider, model, gender, and language with unique constraint on `(provider, tts_model, voice_id)`.
  - Created `catalog_verify_runs`: Immutable log of verification attempts, latencies, and provider errors.
  - Created `org_ai_policy`: Organization-level control over allowed providers, local access, BYOK, S2S, and concurrency caps.
  - Added performance indexes: `workflow_runs(workflow_id, created_at)` and `wallet_ledger(organization_id, created_at)`.
- Updated SQLAlchemy models in `api/db/kodewaves_models.py`.
- Added database client methods in `api/db/kodewaves_client.py` (`list_models`, `upsert_model`, `list_voices`, `upsert_voice`, `record_verify_run`, `get_org_ai_policy`, `upsert_org_ai_policy`).

### 1.2 Audio Test Fixtures
- Initialized bundled 16kHz mono PCM WAV test clips:
  - `tests/fixtures/audio/en_sample.wav`
  - `tests/fixtures/audio/hi_sample.wav`
  - `api/tests/fixtures/audio/en_sample.wav`
  - `api/tests/fixtures/audio/hi_sample.wav`

### 1.3 Provider Alias Normalization
- Created `api/services/catalog/normalize.py`:
  - Canonical function `normalize_provider_name(provider: str) -> str`:
    - `openai_realtime` → `openai`
    - `gemini` / `google_realtime` → `google`
    - `azure_realtime` / `azure_speech` → `azure`
    - `bodhi` → `navana`
    - `grok_realtime` / `xai` → `grok`
    - `ultravox_realtime` → `ultravox`

### 1.4 Dynamic Catalog & Verification Service
- Created `api/services/catalog/catalog_service.py`:
  - Curated seed capabilities for Google Gemini, OpenAI, Anthropic, Groq, Deepgram, Cartesia, ElevenLabs, Sarvam, Azure, Navana, Grok, Ultravox, and local Piper.
  - Capability discovery: `discover_provider(provider, creds)`.
  - Live verification: `verify_layer(provider, layer, creds)` and `verify_provider_all_layers(provider)`.
  - In-memory catalog cache with 60-second TTL and instant invalidation on credential/model mutation (`invalidate_cache()`).
  - Dynamic `get_available_catalog(...)` implementing the visibility formula:
    - Cloud model visible = provider key active in `platform_master_credentials` AND model enabled AND status != 'FAIL'.
    - If no cloud keys configured and local AI is OFF → returns completely empty lists (no fake models).

### 1.5 Route & UI Refactoring
- **`api/routes/catalog.py`**:
  - Deleted static lists (`DEFAULT_CLOUD_LLM_MODELS`, `DEFAULT_CLOUD_STT_MODELS`, `DEFAULT_CLOUD_TTS_MODELS`, `DEFAULT_LOCAL_STT_MODELS`, `DEFAULT_LOCAL_TTS_MODELS`, `DEFAULT_CLOUD_S2S_MODELS`).
  - Routed `GET /catalog/available` directly through `catalog_service.get_available_catalog`.
- **`api/routes/admin/master_keys.py`**:
  - Added `POST /api/v1/admin/master-keys/{provider}/discover`.
  - Added `POST /api/v1/admin/master-keys/{provider}/verify`.
  - Auto-triggers discovery and cache invalidation on `save_master_key` and `delete_master_key`.
- **`api/routes/user.py`**:
  - Connected `GET /configurations/voices/{provider}` to query `voice_catalog` in PostgreSQL.
- **`ui/src/components/VoiceSelectorModal.tsx`**:
  - Removed hardcoded `BUILTIN_FALLBACK_VOICES`. Renders dynamic voices from `/api/v1/user/configurations/voices/...`.

---

## 2. Verification & Test Evidence

### 2.1 Alembic Single-Head Check
Command: `py scripts/check_alembic_single_head.py`
```
[INFO] Current Alembic heads (1): ['b2c3d4e5f6a7']
[SUCCESS] Exactly one head revision found: b2c3d4e5f6a7
```

### 2.2 Import Smoke Test
Command: `py scripts/smoke_test_import.py`
```
[SUCCESS] api.app successfully imported!
```

### 2.3 OpenAPI Route Snapshot
Command: `py scripts/check_openapi_snapshot.py`
```
[INFO] Existing snapshot paths: 433, Current routes paths: 437
[SUCCESS] OpenAPI snapshot verified: 437 endpoints active, 0 regressions.
```

### 2.4 Truth Layer Catalog Unit Tests
Command: `py -m pytest api/tests/test_truth_layer_catalog.py -v`
```
api\tests\test_truth_layer_catalog.py::test_normalize_provider_name PASSED
api\tests\test_truth_layer_catalog.py::test_catalog_visibility_no_keys_empty_manifest PASSED
api\tests\test_truth_layer_catalog.py::test_catalog_visibility_with_google_key PASSED

============================== 3 passed in 1.01s ==============================
```

---

## 3. Exit Gate Confirmation
- [x] Single Alembic head maintained (`b2c3d4e5f6a7`).
- [x] Zero static model/voice lists in `catalog.py`.
- [x] Zero hardcoded fallback voices in `VoiceSelectorModal.tsx`.
- [x] Full visibility formula enforced: Empty keys = empty catalog.
- [x] Provider aliases unified under canonical normalization function.
- [x] OpenAPI snapshot locked to 437 routes with zero regressions.
