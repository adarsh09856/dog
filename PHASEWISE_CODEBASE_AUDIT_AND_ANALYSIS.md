# Kodewaves Codebase File-by-File Audit & Phase-wise Implementation Plan

This document contains the file-by-file technical audit of the Kodewaves platform codebase (`newai.zip` / `stabilize` branch), detailing the exact root causes behind admin-to-user logic breakdowns, credential lifecycle failures, self-hosted local stack issues, routing conflicts, and page-by-page feature gaps, followed by the phase-wise execution plan across Work Packages A through K.

---

## 1. Executive Summary & Verification Context

- **Repository Root**: `e:\ai\aagent\newai`
- **Active Git Branch**: `stabilize`
- **Push Policy**: Strict push gate enforced. **Zero `git push`** until user explicitly responds `CONFIRM PUSH`.
- **Architectural Tenet**: Dynamic Database Truth Layer (`/catalog/available`). Zero hardcoded model/voice lists and zero silent fallbacks.

---

## 2. File-by-File Detailed Code Audit

### 2.1. Admin Master Keys Lifecycle
**File**: `api/routes/admin/master_keys.py`
- **Lines 109–116 (`save_master_key`)**:
  - When a superuser saves credentials for `gemini` or `google`, the route automatically writes two separate records to `PlatformMasterCredentialModel` (`google` and `gemini`). Similar dual-provider logic exists for `azure`/`azure_speech` and `navana`/`bodhi`.
- **Lines 197–205 (`delete_master_key`)**:
  - `stmt = select(PlatformMasterCredentialModel).where(PlatformMasterCredentialModel.provider == provider.lower().strip())`
  - When an admin deletes `gemini`, only the `gemini` row is removed. The `google` row remains intact in PostgreSQL.
  - **Impact**: When `/catalog/available` runs, it checks whether credentials exist for `google`. Because the alias row was never deleted, Google/Gemini models continue to appear in all user dropdowns even after the admin explicitly deleted the key.
  - **Fix**: Symmetrically delete known alias pairs (`gemini` <-> `google`, `azure` <-> `azure_speech`, `navana` <-> `bodhi`) in `delete_master_key`.
- **Lines 138–146, 170–176 (`test_master_key_post` & `test_master_key_connection_path`)**:
  - `success = all(r.get("success", False) for r in results.values())`
  - If a multi-layer provider (e.g. OpenAI offering LLM, STT, and TTS) succeeds on LLM and TTS but fails on STT, `success` evaluates to `False`. The route sets `status_str = "invalid"` and calls `update_master_credential_health(provider, "invalid")`.
  - **Impact**: Marking the entire credential invalid can disrupt layers that are fully operational.
  - **Fix**: Surface layer-level health status in DB and response metadata rather than marking the credential globally invalid when only an optional secondary layer fails.

---

### 2.2. Admin Platform Settings
**File**: `api/routes/admin/settings.py`
- **Lines 57–108 (`get_all_platform_settings`)**:
  - Indentation breakdown: Lines 67–108 are indented 8 spaces, placing them entirely inside the `except Exception:` block of line 64.
  - **Impact**: When settings retrieval succeeds normally, execution exits the `try` block and completely bypasses lines 67–108. The function reaches the end without hitting a `return` statement, implicitly returning `None`. FastAPI then fails response validation against `PlatformSettingsResponse`, resulting in an unhandled 500 Internal Server Error whenever the admin loads the settings page.
  - **Fix**: Unindent lines 67–108 by 4 spaces so that `return PlatformSettingsResponse(...)` executes following the `try/except` block.
- **Lines 111–226 (`update_platform_settings`)**:
  - When platform settings (branding, BYOK policy, wallet policy, local AI engine endpoints, concurrency limits) are updated, the function writes them to `GlobalPlatformSettingModel` and returns `{"message": "..."}`.
  - It **never calls `catalog_service.invalidate_cache()`**.
  - **Impact**: Changes made to `enable_local_ai_engine`, `local_ai_access_policy`, or BYOK rules do not take effect immediately; user catalog views continue serving cached data for 60 seconds or until a worker restart.
  - **Fix**: Call `catalog_service.invalidate_cache()` immediately after updating platform settings.

---

### 2.3. Model Catalog Truth Layer & Verification Probes
**File**: `api/services/catalog/catalog_service.py`
- **Lines 604–611 (`verify_layer`)**:
  ```python
  models = await kodewaves_db_client.list_models(layer=layer_norm, provider=prov_norm, enabled_only=False)
  for m in models:
      m.status = status_str
      m.latency_ms = latency_ms
      m.last_verified_at = datetime.now(UTC)
      m.last_error = error_msg if not success else None
  ```
  - `kodewaves_db_client.list_models()` creates and closes its own SQLAlchemy session context (`async with self.get_session() as session:`). The returned objects `models` are detached ORM instances.
  - Modifying attributes on detached instances without adding them to an active session or calling `session.commit()` only changes values in ephemeral memory.
  - **Impact**: Model verification status (`PASS` / `FAIL`), latency, and error timestamps are never committed to the `ai_model_catalog` table in PostgreSQL. The database catalog status remains permanently frozen as `"UNTESTED"`.
  - **Fix**: Implement `update_model_verification_status` in `KodewavesDBClient` with an explicit `session.commit()` and call it in `verify_layer`.
- **Lines 291 & 559 (`piper` default endpoint)**:
  - Default URL was previously set to `http://piper:8766`, whereas the Docker Compose service maps port `5000`. (Addressed in commit `f2963f18`).
- **Lines 644–794 (`get_available_catalog`)**:
  - Previously included local AI models without probing service availability. (Resolved in commit `f2963f18` with dynamic HTTP health checks against Whisper `/v1/models` and Piper `/voices`).

---

### 2.4. Database Client Idempotency & Persistence
**File**: `api/db/kodewaves_client.py`
- **Lines 435–467 (`add_minutes`)**:
  - Updates `OrganizationWalletModel.credit_balance_minutes` and writes a record to `WalletLedgerModel`.
  - It does not check if a ledger entry with `reference_id` already exists.
  - **Impact**: During payment flows, the frontend client calls `POST /payments/verify` (passing the Razorpay payment ID), and Razorpay asynchronously dispatches a `payment.captured` webhook to `POST /payments/razorpay/webhook` (with the same payment ID). Because `add_minutes` lacks idempotency on `reference_id`, the organization is credited twice for a single purchase.
  - **Fix**: In `add_minutes`, check if `reference_id` is provided and already exists in `WalletLedgerModel`. If present, return the existing wallet without applying duplicate minutes.
- **Model Verification Method**:
  - `KodewavesDBClient` lacks a dedicated helper to update model verification state in bulk or per-provider.
  - **Fix**: Add `update_model_verification_status(provider, layer, status, latency_ms, error_message)` with transactional commit.

---

### 2.5. Sovereign Configuration Resolver
**File**: `api/services/configuration/kodewaves_resolver.py`
- **Lines 142–159 (`_detect_provider_from_stt_model`)**:
  ```python
  if "whisper" in ml:
      return "openai"
  ```
  - Any model string containing `"whisper"` automatically maps to `openai`.
  - **Impact**: When a user configures Groq Whisper (`whisper-large-v3`, `whisper-large-v3-turbo`) or local Faster-Whisper, the resolver searches for OpenAI credentials instead of Groq or local endpoints. If the organization only holds a Groq API key, STT resolution throws HTTP 400.
  - **Fix**: Differentiate providers in `_detect_provider_from_stt_model`:
    - If `ml.startswith("groq/")` or `ml in ("whisper-large-v3", "whisper-large-v3-turbo")`: return `"groq"`.
    - If `ml in ("faster-whisper", "whisper-local")` or `"sovereign"` in ml: return `"whisper"`.
    - Otherwise, default to `"openai"`.
- **Lines 317–320 (`local_ai_access_policy`)**:
  - Previously checked only `"all_workspaces"`, causing mismatch with the default `"public"` policy. (Resolved in commit `f2963f18`).

---

### 2.6. Pipecat Service Factory & Silent Fallbacks
**File**: `api/services/pipecat/service_factory.py`
- **Lines 946–1010 (`get_tts_service`)**:
  - When user-configured TTS fails or credentials cannot be resolved:
    ```python
    cartesia_key = os.environ.get("CARTESIA_API_KEY")
    if cartesia_key: return CartesiaTTSService(...)
    gemini_key = os.environ.get("GEMINI_API_KEY") ...
    elevenlabs_key = os.environ.get("ELEVENLABS_API_KEY") ...
    openai_key = os.environ.get("OPENAI_API_KEY") ...
    return PiperHttpTTSService(...)
    ```
  - **Impact**: If a user selects Cartesia or Gemini TTS and their credential is not configured, the engine silently falls back to arbitrary environment keys or local Piper CPU. Calls sound completely different without any warning or error, obscuring underlying configuration issues.
  - **Fix**: Adhere strictly to the V4 zero silent fallback policy: raise a descriptive `ValueError` or HTTP 400 when credentials for the requested provider are missing.

---

### 2.7. Call Billing & Local Call Accounting
**File**: `api/services/workflow_run_billing.py`
- **Lines 99–109 (`report_workflow_run_platform_usage`)**:
  - The check to grant free local calls currently relies on loose context flags:
    ```python
    if (getattr(workflow_run, "mode", None) == "local" or init_ctx.get("is_local") or gath_ctx.get("is_local") or init_ctx.get("source") == "local"):
        return
    ```
  - When the resolver runs, it sets `effective.resolution_info = {"overall_source": "local", ...}`. If the runner does not copy `is_local` to `initial_context`, local calls are billed against the organization's voice minutes.
  - **Fix**: Check `usage_info.get("resolution_info", {}).get("overall_source") == "local"` and `init_ctx.get("resolution_info", {}).get("overall_source") == "local"` to ensure local calls are never billed.

---

### 2.8. Campaigns API & Lifecycle Gaps
**File**: `api/routes/campaign.py`
- **Existing Endpoints**:
  - `POST /create`, `GET /`, `GET /{id}`, `POST /{id}/start`, `POST /{id}/pause`, `POST /{id}/resume`, `PATCH /{id}`, `GET /{id}/runs`, `POST /{id}/redial`, `GET /{id}/progress`, `GET /{id}/source-download-url`, `GET /{id}/report`, `GET /{id}/traffic-stats`.
- **Identified Gaps**:
  1. **No Cancel/Stop Endpoint**: Users can pause a campaign, but there is no endpoint to permanently cancel/stop it.
  2. **No Delete/Archive Endpoint**: Campaigns cannot be deleted or archived (`DELETE /{id}` missing).
  3. **No Pre-flight Validation Endpoint (`GET /{id}/preflight`)**: The UI cannot display clear blocker banners (e.g. unverified telephony, unpublished agent, wallet depleted, empty contact list) before the user clicks Start.
  4. **Dialer Offline Banner**: UI lacks health status link to check if `campaign_orchestrator` is actively heartbeating.
- **Fix**: Implement `POST /{id}/cancel`, `DELETE /{id}`, and `GET /{id}/preflight` in `api/routes/campaign.py`.

---

### 2.9. CRM Leads API Gaps
**File**: `api/routes/crm.py`
- **Existing Endpoints**:
  - `GET /stages`, `POST /stages`, `GET /contacts`, `POST /contacts`, `PUT /contacts/{id}`, `DELETE /contacts/{id}`.
- **Identified Gaps**:
  1. `PUT /stages/{stage_id}`: Cannot update stage name, color, or metadata.
  2. `DELETE /stages/{stage_id}`: Cannot remove a lead stage.
  3. `POST /stages/reorder`: Cannot reorder kanban columns.
  4. `POST /contacts/import-csv`: Cannot bulk import contacts from CSV.
  5. `GET /contacts/export-csv`: Cannot export filtered contacts to CSV.
  6. `GET /contacts/{contact_id}/timeline`: Cannot view call history, transcripts, and notes for a contact.
- **Fix**: Implement the missing CRUD, import/export, and timeline routes in `api/routes/crm.py`.

---

### 2.10. Organization Status Gate & Telephony Verification
**Files**: `api/db/models.py`, `api/routes/organization.py`
- **Missing `status` on Organization**:
  - `OrganizationModel` in `api/db/models.py` has no `status` column.
  - Requirements state that organizations must support statuses: `active`, `past_due`, `churned`, `suspended`.
  - Non-active orgs must be blocked from initiating calls, launching campaigns, or embedding widgets.
  - **Fix**: Add `status = Column(String, default="active", nullable=False)` to `OrganizationModel` with an Alembic migration and enforce checks at runtime.
- **Telephony Provider Verification**:
  - `api/routes/organization.py` provides telephony CRUD (`/telephony-configs`), default assignment, and phone number mapping, but lacks a test endpoint to verify carrier credentials against provider APIs.
  - **Fix**: Add `POST /telephony-configs/{config_id}/verify` to test provider connectivity.

---

### 2.11. Prompt Templates API Gaps
**File**: `api/routes/prompt_templates.py`
- **Existing Endpoints**: `GET ""`, `POST ""`, `DELETE "/{template_id}"`.
- **Identified Gap**: Missing `PUT "/{template_id}"`.
  - **Impact**: Updating an existing prompt template fails from the UI, forcing users to delete and recreate templates.
  - **Fix**: Add `PUT "/{template_id}"` supporting title, description, content, and category updates.

---

### 2.12. Next.js Middleware & Web Widget Access
**File**: `ui/src/middleware.ts`
- **Lines 8 & 90–102**:
  - `PUBLIC_PATHS = ['/', '/pricing', '/auth', '/handler', '/embed']`
  - Matcher regex excludes static image and font extensions, but does **not** exclude `.js`.
  - **Impact**: When an external website embeds `<script src="https://example.com/widget.js"></script>`, the request matches the private tenant middleware, finds no session token, and responds with a 307 redirect to `/auth/login`. This prevents the widget from loading for external website visitors.
  - **Fix**: Add `/widget.js` to `PUBLIC_PATHS` and update the matcher regex to bypass `/widget.js`.

---

## 3. Phase-wise Implementation Plan (Work Packages A to K)

### Phase 1: Background Infrastructure & Process Health (WP-A & WP-B)
*Status: Completed & committed locally in `6f104b25` and `f2963f18`.*
1. Enabled `ENABLE_CAMPAIGN_ORCHESTRATOR=true` in `install.sh`, `start_services_docker.sh`, and AAPanel configurations.
2. Implemented 5s Redis heartbeat loop (`campaign:orchestrator:heartbeat`, 15s TTL) in `campaign_orchestrator.py`.
3. Added `GET /monitoring/process-health` in `api/routes/admin/monitoring.py` reporting live health of Postgres, Redis, MinIO, Orchestrator, Ollama, Piper, and Whisper.
4. Corrected Piper port to `5000` in `catalog_service.py` and added `WHISPER_ENDPOINT` in Docker Compose.
5. Added dynamic HTTP health probes to `get_available_catalog` so local models are only listed when backend services respond with HTTP 200.

---

### Phase 2: Truth Layer Persistence & Key Lifecycle (WP-C)
*Target: Fix model status persistence and symmetric key deletion.*
1. **`api/db/kodewaves_client.py`**:
   - Implement `update_model_verification_status(provider, layer, status, latency_ms, error_message)` with transactional session management.
2. **`api/services/catalog/catalog_service.py`**:
   - Call `update_model_verification_status` inside `verify_layer` so `PASS`/`FAIL` states are saved to PostgreSQL.
3. **`api/routes/admin/master_keys.py`**:
   - Update `delete_master_key` to delete associated alias rows (`gemini`/`google`, `azure`/`azure_speech`, `navana`/`bodhi`).
   - Call `catalog_service.invalidate_cache()` after credential operations.
   - Refactor `test_master_key` to avoid setting the entire credential invalid when only a secondary layer fails.

---

### Phase 3: Resolver Routing & Zero Silent Fallback (WP-D & WP-E)
*Target: Clean up provider detection and eliminate silent fallbacks.*
1. **`api/services/configuration/kodewaves_resolver.py`**:
   - Update `_detect_provider_from_stt_model` to distinguish between Groq Whisper, local Faster-Whisper, and OpenAI Whisper.
2. **`api/services/pipecat/service_factory.py`**:
   - Remove silent fallbacks in `get_tts_service` (lines 946–1010). Raise explicit errors when requested provider credentials are not found.
3. **`api/services/pipecat/gemini_stt.py` & `gemini_tts.py`**:
   - Ensure errors during synthesis or transcription propagate cleanly to the call event log.

---

### Phase 4: Campaign Pre-flight & Full Lifecycle (WP-F)
*Target: Complete campaign workflow endpoints.*
1. **`api/routes/campaign.py`**:
   - Add `GET /{campaign_id}/preflight`: checks telephony outbound readiness, agent publication status, wallet balance, calling window, and contact list count.
   - Add `POST /{campaign_id}/cancel`: transitions running/paused campaign to `CANCELLED`.
   - Add `DELETE /{campaign_id}`: archives or removes the campaign.
2. **Orchestrator Integration**:
   - Ensure pre-flight checks verify active orchestrator heartbeat before allowing campaign starts.

---

### Phase 5: Org Status Gate & Billing Idempotency (WP-G & WP-H)
*Target: Enforce org-level access control and idempotent wallet billing.*
1. **`api/db/models.py` & Alembic Migration**:
   - Add `status` column (`active`, `past_due`, `churned`, `suspended`, default `"active"`) to `OrganizationModel`.
   - Generate Alembic revision for schema consistency.
2. **Runtime Status Enforcement**:
   - Validate org status on workflow run start, campaign batch execution, and widget initialization.
3. **`api/db/kodewaves_client.py:add_minutes`**:
   - Add idempotency check on `reference_id` against `WalletLedgerModel` to prevent duplicate billing from concurrent webhooks.
4. **`api/services/workflow_run_billing.py`**:
   - Ensure local calls (`overall_source == "local"`) and admin test calls are billed 0 minutes based on typed resolution metadata.

---

### Phase 6: Page-by-Page Feature Gaps (WP-I)
*Target: Close identified gaps across the 17 product pages.*
1. **Admin Settings (`api/routes/admin/settings.py`)**:
   - Fix 8-space indentation bug in `get_all_platform_settings`.
   - Add `catalog_service.invalidate_cache()` to `update_platform_settings`.
2. **CRM Leads (`api/routes/crm.py`)**:
   - Add `PUT /stages/{stage_id}`, `DELETE /stages/{stage_id}`, and `POST /stages/reorder`.
   - Add `POST /contacts/import-csv` and `GET /contacts/export-csv`.
   - Add `GET /contacts/{contact_id}/timeline`.
3. **Prompt Templates (`api/routes/prompt_templates.py`)**:
   - Add `PUT /{template_id}` endpoint.
4. **Telephony Verification (`api/routes/organization.py`)**:
   - Add `POST /telephony-configs/{config_id}/verify` to validate credentials with carrier APIs.
5. **Widget Public Access (`ui/src/middleware.ts`)**:
   - Add `/widget.js` to public paths and bypass list in middleware matcher.

---

### Phase 7: Repository Hygiene & Local Test Verification (WP-J & WP-K)
*Target: Codebase cleanup, testing protocol, and push gate compliance.*
1. **Repo Cleanup**:
   - Untrack `.claude/` directory and ensure proper `.gitignore` entries.
2. **Local Test Verification**:
   - Execute test harness across local services (Postgres, Redis, MinIO, Ollama, Piper, Whisper).
   - Label test outputs with evidence tags (`LOCAL-REAL`, `LOCAL-SIM`, `CLOUD-REAL`, `STAGING-ONLY`).
   - Generate `reports/local_test_report.md`.
3. **Push Gate**:
   - Maintain all work on local `stabilize` branch.
   - Wait for explicit user confirmation (`CONFIRM PUSH`) before any remote push.
