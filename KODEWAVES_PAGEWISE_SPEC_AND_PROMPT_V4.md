# Kodewaves V4: Page-wise Spec, Local Test Plan, Push Gate, Antigravity Prompt

Companion to `KODEWAVES_COMPLETE_PLAN_AND_PROMPT.md` and codebase truth layer on branch `stabilize`. This file details **every page in detail**, **verified code facts & root causes**, **the 11 Work Packages (A to K)**, **local test plan**, and **push gate**.

Evidence labels (all test results tagged with one):
- `LOCAL-REAL`: real local services (Postgres, Redis, MinIO, Ollama, Piper, Whisper, browser WebRTC)
- `LOCAL-SIM`: simulated carrier or provider stub (proves our code path only)
- `CLOUD-REAL`: real cloud provider call with a real key (Gemini etc.)
- `STAGING-ONLY`: needs a public URL or real phone (carrier calls)

---

## Verified Codebase Facts (Branch `stabilize`)

1. **Alembic Single Head**: Exactly 1 head confirmed (`b2c3d4e5f6a7 (head)`) across 103 migration files.
2. **Campaign Orchestrator Disabled**: `install.sh:318`, `docker-compose.aapanel.yaml:134`, `scripts/start_services_docker.sh:88` default `ENABLE_CAMPAIGN_ORCHESTRATOR=false`.
3. **Local AI Policy Mismatch**: `scripts/seed_platform.py:84` sets `"all_workspaces"`, while `kodewaves_resolver.py:316` requires `"public"`.
4. **Detached ORM Mutation**: `catalog_service.py:607` mutates `m.status` outside a session without commit; verification results never persist.
5. **Local Endpoint Blindness**: `catalog_service.py:740` hardcodes local STT/TTS without live endpoint probes.
6. **Incomplete Layer Probes**: `verify_layer` never synthesizes test audio, transcribes test audio, or handshakes S2S; typed keys only sent to LLM; single layer failure marks entire provider invalid.
7. **Whisper Routing Bug**: `kodewaves_resolver.py:148` maps any STT model containing `"whisper"` to OpenAI, breaking Groq `whisper-large-v3` and local Whisper.
8. **Silent Fallback Bug**: `service_factory.py:946-1010` silently falls back to env-var keys and Piper.
9. **Gemini Streaming & Error Handling**: `gemini_stt.py` and `gemini_tts.py` swallow errors and use non-streaming REST wrappers.
10. **Org Status Missing**: `OrganizationModel` lacks `status` column (`active / past_due / churned / suspended`) and enforcement gates.
11. **Billing Local Source Check**: `workflow_run_billing.py:101` checks context flags instead of `resolution_info.overall_source == "local"`.
12. **Compose WHISPER_ENDPOINT Missing**: `WHISPER_ENDPOINT` omitted in Compose files; Piper fallback port mismatch (`8766` vs `5000`).
13. **Repo Hygiene**: `.claude/` tracked in git; `kodewaves-plugins` has nested `.git`.
14. **Asymmetric Key Deletion**: `api/routes/admin/master_keys.py:delete_master_key` deletes only one alias (`gemini` vs `google`), leaking models in catalog.
15. **Admin Settings Indentation Bug**: `api/routes/admin/settings.py:67-108` indented inside `except Exception:`, returning `None` on success, and lacks cache invalidation.

---

## A. Shared Foundations

1. **Auth and Org**: Signup, login, JWT, org auto-created with wallet, plan, bonus minutes. Roles: superuser, org admin, member. Impersonate (admin) audit-logged and visibly bannered in UI.
2. **Catalog Truth Layer** (`/catalog/available`): Only source of model/voice dropdowns. Key present + layer probe PASS → visible. Key removed → gone within 60 s. Per-org policy (local allowed, S2S allowed).
3. **Resolver** (`kodewaves_resolver.py`): Turns an agent's model config into live services. Zero silent fallback: missing key = clear HTTP 400 shown in UI and call log.
4. **Org Status Gate**: `active / past_due / churned / suspended` checked on run start, campaign start, campaign batch, widget/embed init.
5. **Wallet**: Minutes deducted per call (S2S multiplier), local and admin-test calls free (0 minutes), frozen wallet blocks, zero wallet blocks only paid-cloud calls.
6. **Background Processes**: API workers, ARQ worker, campaign orchestrator, ARI manager. Health shown in Admin → Monitoring.
7. **Error Surfacing**: Every failure becomes a visible call event on the run page (`stt_silent`, `tts_error`, `carrier_rejected`, `wallet_empty`, `org_suspended`, `model_unresolved`).

---

## B. Page-by-Page Specification (17 Core Areas)

### 1. Overview (`/overview`)
- **Shows**: Active agents, calls today, minutes used, wallet balance, running campaigns, recent runs, failed runs count, system warnings.
- **Logic**: Computed from live DB; empty state links to onboarding steps.
- **Onboarding Checklist**: Key present → agent created → test call done → telephony added → campaign run.
- **Tests**: Seed runs match DB counts; wallet reflects after call (`LOCAL-REAL`).

### 2. Voice Agents (`/workflow`, create, editor)
- **Features**: Templates gallery, draft/publish versioning, duplicate, archive, node-graph editor, Hindi/English/mixed language, voice picker, pre-recorded clips, dictionary, embed dialog, tester panel.
- **Rules**: Model editor shows only `/catalog/available` items; validation blocks publish if start node missing, tools disconnected, models unresolved. Resolved source badge displayed.
- **Tests**: Create agent → validate → publish → browser test call in Hindi and English (`LOCAL-REAL` with local models; `CLOUD-REAL` with Gemini).

### 3. Campaigns (`/campaigns`)
- **Features**: A/B agent split, telephony config, CSV upload, calling window (IST default), max concurrency, retry rules, DND list, caller ID, variable mapping, live progress, redial failed, download report.
- **Gaps to Close**: Stop/cancel (`POST /campaigns/{id}/cancel`), delete/archive (`DELETE /campaigns/{id}`), pre-start blockers check (`GET /campaigns/{id}/preflight`).
- **Rules**: Pre-flight blocks if no outbound telephony, agent unpublished, wallet 0 for paid models, org inactive, outside calling window. Dialer offline banner if orchestrator process down. Concurrency obeys `local_ai_max_concurrency`. Circuit breaker pauses on repeated carrier failures.
- **Tests**: `LOCAL-SIM` with stub carrier for 5 contacts (dispatch, retry, window, pause/resume, circuit breaker, wallet-0 block, suspended-org block).

### 4. Models (`/model-configurations`)
- **Shows**: Org default model configuration, BYOK keys, resolved-source badges.
- **Rules**: Dropdown = catalog only; BYOK key test probes each layer; unresolvable configurations rejected with reason; "Auto" shows what it resolves to.
- **Tests**: Save configuration per layer, run call, verify recorded provider/model matches (`LOCAL-REAL` / `CLOUD-REAL`).

### 5. Telephony (`/telephony-configurations`)
- **Providers**: Twilio, Plivo, Telnyx, Vonage, Cloudonix, Exotel, Vobiz, Asterisk ARI.
- **Features**: CRUD configs, mark default, inbound number mapping, outbound-ready check, webhook URL display with copy button, signature verification status.
- **Gaps to Close**: Add live credentials test endpoint (`POST /organizations/telephony-configs/{id}/verify`) calling upstream carrier API.
- **Tests**: `LOCAL-SIM` signature simulator for inbound; outbound readiness validation.

### 6. Tools (`/tools`)
- **Features**: HTTP API tool, MCP tool, transfer-call, transfer-agent, end-call, built-in CRM/calendar tools.
- **Rules**: Secrets masked in UI and logs; test dialog runs tool with sample variables and displays request/response; in-call tool errors spoken gracefully.
- **Tests**: Mock HTTP server tool called live during test call (`LOCAL-REAL`).

### 7. Files / Knowledge Base (`/files`)
- **Features**: PDF/DOCX/TXT/CSV upload, processing status, chunk preview, delete, attach to agent.
- **Rules**: Embeddings use verified model from catalog; pgvector index; configurable top-k and threshold.
- **Tests**: Upload document → ready → agent answers question based on document (`LOCAL-REAL`).

### 8. Recordings (`/recordings`)
- **Features**: Pre-recorded clips per agent, TTS cache viewer with clear cache; call recordings streamed via MinIO signed URLs (`s3_signed_url`).
- **Tests**: Upload clip, agent plays it; call recording playable after test call (`LOCAL-REAL`).

### 9. CRM Leads (`/crm`)
- **Features**: Kanban by stage, filters, search, per-lead call history, notes, owner, "call now", "add to campaign", stage update on call outcome.
- **Gaps to Close**: Stage edit/delete/reorder (`PUT/DELETE /crm/stages/{id}`, `PUT /crm/stages/reorder`), CSV import/export (`POST /crm/contacts/import-csv`, `GET /crm/contacts/export`), contact timeline (`GET /crm/contacts/{id}/timeline`).
- **Tests**: Call outcome moves lead stage; import leads; add to campaign (`LOCAL-SIM`).

### 10. Appointments (`/appointments`)
- **Features**: Calendar and list views, working hours, slot length, buffer, booking by voice agent via built-in tool, reschedule/cancel by voice.
- **Rules**: Conflict checking refuses double booking and offers alternatives.
- **Tests**: Agent books slot during call; conflicting booking refused (`LOCAL-REAL`).

### 11. Voice Forms (`/forms`)
- **Features**: Field types, validation, spoken questions, retry on invalid answer, submission export, link form to agent.
- **Tests**: Agent collects form by voice; invalid input re-asked; submission saved (`LOCAL-REAL`).

### 12. Web Widgets (`/widgets`)
- **Features**: Appearance, allowed domains, copy snippet, preview, usage stats.
- **Rules**: `widget.js` served anonymously (Next.js middleware must not redirect to login); allowed-domain enforcement; org status and wallet checked at init.
- **Tests**: Load snippet on external HTML page, WebRTC audio connects; blocked on unauthorized domain or suspended org (`LOCAL-REAL`).

### 13. Prompt Templates (`/prompt-templates`)
- **Features**: Categories, language tags, variables, starter templates in Hindi and English.
- **Gaps to Close**: Add update endpoint (`PUT /prompt-templates/{id}`).
- **Tests**: Create, edit, apply to agent; variables resolve at call time.

### 14. Agent Runs (`/usage`)
- **Features**: Filter by agent/campaign/status/date/mode, run detail with transcript, audio, events timeline, resolved providers, latency per turn, cost in minutes, error reason, redial, CSV export.
- **Rules**: Failed runs show structured reason codes (`stt_silent`, `tts_error`, `carrier_rejected`, `wallet_empty`, `org_suspended`, `model_unresolved`).
- **Tests**: Completed and deliberately failed calls record accurate reasons (`LOCAL-REAL`).

### 15. Sovereign Wallet (`/billing-sovereign`)
- **Features**: Balance, ledger, packages, plans, subscribe, invoices, low-balance threshold.
- **Rules**: HMAC verified webhooks; idempotent crediting (same `reference_id` never credits twice); ledger entry per deduction with run ID; S2S multiplier applied; 100% local calls deduct 0 minutes.
- **Tests**: Simulated signed Razorpay webhook credits once even if retried; local calls deduct 0 (`LOCAL-SIM`).

### 16. Reports (`/reports`)
- **Features**: Date range, agent/campaign filter, totals (calls, answered, duration, minutes, cost), outcome breakdown, charts, CSV export.
- **Tests**: Report totals equal sum of Agent Runs for same filter.

### 17. Sovereign Admin (`/admin/*`)
- **Sub-pages**: Overview, Master Keys, Models, Settings, Users, Plans, Credit Packages, Moderation, Monitoring, Audit Logs.
- **Gaps to Close**:
  - Add `GET /admin/monitoring/process-health` panel (API, ARQ, Orchestrator, Redis, Postgres, MinIO, Local AI).
  - Fix indentation bug in `api/routes/admin/settings.py` and call `catalog_service.invalidate_cache()`.
  - Fix alias deletion in `api/routes/admin/master_keys.py`.
- **Tests**: Admin actions write audit rows; kill-call terminates live session; local AI toggle hides local models in catalog within 60s.

---

## C. Cloud and Self-Hosted Matrix

| Mode | LLM | STT | TTS | Requirements |
|---|---|---|---|---|
| Cloud (Gemini-only) | Gemini | Gemini audio-in | Gemini TTS | One Google AI Studio key |
| Cloud (India best) | Gemini | Sarvam or Deepgram | Sarvam / Cartesia / ElevenLabs | 2 to 3 keys |
| S2S | Gemini Live or OpenAI Realtime | built-in | built-in | One key, S2S multiplier |
| Fully self-hosted | Ollama (`qwen2.5:0.5b`) | Faster-Whisper (`Systran/tiny`) | Piper ONNX (`hi_IN`, `en_US`) | 8 GB RAM, no keys, 0 min cost |

---

## D. Work Packages Execution Plan (A to K)

### WP A: Background Processes & Health Gating
- Default `ENABLE_CAMPAIGN_ORCHESTRATOR=true` in `install.sh`, `docker-compose.aapanel.yaml`, `scripts/start_services_docker.sh`.
- Implement `GET /admin/monitoring/process-health` in `api/routes/admin/monitoring.py`.
- Display dialer offline banner if orchestrator process is unavailable.
- Files: `docker-compose.aapanel.yaml`, `install.sh`, `scripts/start_services_docker.sh`, `api/routes/admin/monitoring.py`.

### WP B: Local AI Engine Policy & Live Health Probing
- Unify `local_ai_access_policy` default to `"public"` across `scripts/seed_platform.py` and resolver.
- Add `WHISPER_ENDPOINT` to Compose files.
- Fix Piper internal port fallback to `http://piper:5000`.
- Probe Whisper and Piper endpoints live in `catalog_service.py:get_available_catalog` before adding to manifest.
- Files: `docker-compose.aapanel.yaml`, `docker-compose.yaml`, `scripts/seed_platform.py`, `api/services/catalog/catalog_service.py`.

### WP C: Real Verification Probes & Persisted Catalog Status
- Fix detached ORM update bug: persist verification runs with an active SQLAlchemy session and commit.
- Upgrade `verify_layer` with real synthesis, transcription, and socket handshake checks.
- Pass typed credentials through all layers during test runs.
- Prevent single-layer failure from invalidating unrelated provider capabilities.
- Files: `api/services/catalog/catalog_service.py`, `api/db/kodewaves_client.py`, `api/routes/admin/master_keys.py`.

### WP D: Provider Registry Unification & Strict No-Silent-Fallback
- Route Groq Whisper STT to Groq in `kodewaves_resolver.py`.
- Add builders in `service_factory.py` for Groq Whisper, Deepgram Aura TTS, Azure STT/TTS, Cartesia Ink.
- Eliminate silent fallback to env keys and Piper; return HTTP 400 when keys are missing.
- Files: `api/services/configuration/kodewaves_resolver.py`, `api/services/pipecat/service_factory.py`.

### WP E: Gemini Voice Path & Model Coercion
- Streamline `gemini_stt.py` and `gemini_tts.py`: proper error propagation, dynamic voice support.
- Eliminate fragmented model string coercions.
- Files: `api/services/pipecat/gemini_stt.py`, `api/services/pipecat/gemini_tts.py`.

### WP F: Campaign Lifecycle & Pre-Flight Blockers
- Implement `POST /campaigns/{id}/cancel`, `DELETE /campaigns/{id}`, `GET /campaigns/{id}/preflight`.
- Enforce `local_ai_max_concurrency` cap on campaign dispatches using local models.
- Implement circuit breaker for repeated carrier failures.
- Files: `api/routes/campaign.py`, `api/services/campaign/orchestrator.py`.

### WP G: Organization Status Gate & Lifecycle Enforcement
- Add Alembic migration adding `status` enum (`active`, `past_due`, `churned`, `suspended`) to `organizations`.
- Add `OrganizationStatusGate` check on run start, campaign start/batch, and widget init.
- Files: `api/alembic/versions/*_add_org_status.py`, `api/db/models.py`, `api/services/auth/org_gate.py`, route files.

### WP H: Billing, Wallet Invariants & Webhook Idempotency
- Make `kodewaves_db_client.add_minutes` idempotent based on `reference_id`.
- Check `resolution_info.overall_source == "local"` in `workflow_run_billing.py` to ensure 0-minute deduction.
- Validate raw request bytes HMAC on Razorpay and Stripe webhooks.
- Files: `api/db/kodewaves_client.py`, `api/routes/payments.py`, `api/services/workflow_run_billing.py`.

### WP I: 17 Product Pages & UI/API Gaps
- Allow anonymous access to `/widget.js` in `ui/src/middleware.ts`.
- Fix indentation in `api/routes/admin/settings.py` and add cache invalidation.
- Fix symmetric key alias deletion in `api/routes/admin/master_keys.py`.
- Add missing CRM routes (stage edit/delete/reorder, CSV import/export, timeline).
- Add `PUT /prompt-templates/{id}`.
- Add `POST /organizations/telephony-configs/{id}/verify`.
- Files: `ui/src/middleware.ts`, `api/routes/admin/settings.py`, `api/routes/admin/master_keys.py`, `api/routes/crm.py`, `api/routes/prompt_templates.py`, `api/routes/organization.py`.

### WP J: Security, Isolation & Repo Hygiene
- Untrack `.claude/` from git index.
- Remove nested `.git` inside `kodewaves-plugins`.
- Ensure cache folders and `.zip` remain untracked in `.gitignore`.
- Files: `.gitignore`, Git index.

### WP K: Local Verification Harness & Reporting
- Build `scripts/e2e/local_stack_verification.py`.
- Run tests and produce `reports/local_test_report.md`.
- Files: `scripts/e2e/local_stack_verification.py`, `reports/local_test_report.md`.

---

## E. Local Test Plan & Push Gate

1. All development performed strictly on branch `stabilize`.
2. Commit locally per work package with message prefix `feat(wp-X): ...`.
3. Start stack locally: `docker compose --profile local up -d --build`.
4. Run integration suite and UI tests.
5. Produce `reports/local_test_report.md` with honest labels (`LOCAL-REAL`, `LOCAL-SIM`, `CLOUD-REAL`, `STAGING-ONLY`).
6. **Push Gate**: **NO `git push`** until the report is reviewed and user explicitly confirms with `CONFIRM PUSH`.
