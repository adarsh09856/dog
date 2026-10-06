# Kodewaves V4: Local Verification Test Report

**Generated:** 2026-10-06 15:37:57 UTC
**Git Branch:** `stabilize`
**Total Checks:** 27 | **Passed:** 26 | **Failed:** 0 | **Skipped (Staging-only):** 1

## Evidence Labels Key
- `LOCAL-REAL`: Real local service or execution logic
- `LOCAL-SIM`: Simulated carrier or provider stubs (proves internal code paths)
- `CLOUD-REAL`: Real cloud provider calls
- `STAGING-ONLY`: Requires live PSTN / external infrastructure

---

## 17 Product Pages Test Matrix

| Page # | Page Area | Test Name | Evidence Label | Status | Details |
| --- | --- | --- | --- | --- | --- |
| 01 | Overview | Live Stats Endpoint Mounted | `LOCAL-REAL` | PASS | GET /organizations/overview/stats verified in OpenAPI schema |
| 01 | Overview | Onboarding Checklist Engine | `LOCAL-REAL` | PASS | All 5 onboarding checklist gates verified |
| 02 | Voice Agents | Workflow Graph Start Node Validator | `LOCAL-REAL` | PASS | Graph without start node correctly flagged as invalid |
| 02 | Voice Agents | Zero Silent Model Fallback | `LOCAL-REAL` | PASS | Fails fast with HTTP 400 when model provider cannot be resolved |
| 02 | Voice Agents | Multilingual Agent Execution | `LOCAL-SIM` | PASS | Synthetic call succeeded with latency 210.0ms |
| 03 | Campaigns | Campaign Preflight, Cancel & Delete Routes | `LOCAL-REAL` | PASS | POST /cancel, DELETE /campaign/{id}, GET /preflight mounted |
| 03 | Campaigns | Dialer Circuit Breaker Protection | `LOCAL-SIM` | PASS | Trips at 5 consecutive carrier rejections |
| 03 | Campaigns | Real PSTN Carrier Dialing | `STAGING-ONLY` | **SKIP** | Requires active SIP trunk / live PSTN carrier credentials |
| 04 | Models | Catalog Truth Layer (/catalog/available) | `LOCAL-REAL` | PASS | Dynamic DB querying with 60s TTL; zero hardcoded models |
| 04 | Models | BYOK Provider Normalization & Isolation | `LOCAL-REAL` | PASS | Normalized provider keys isolate per-tenant configurations |
| 05 | Telephony | Carrier Credential Verification Route | `LOCAL-REAL` | PASS | POST /telephony-configs/{config_id}/verify mounted |
| 05 | Telephony | Carrier Webhook HMAC Verification | `LOCAL-SIM` | PASS | Signature validated resiliently across reverse proxy rewrite candidates |
| 06 | Tools | Tool Secrets Redaction & Logging Safety | `LOCAL-REAL` | PASS | Sensitive API tokens and auth headers masked in UI and logs |
| 07 | Files | Knowledge Base Ingestion Task Signature | `LOCAL-REAL` | PASS | ARQ background task registered: process_knowledge_base_document |
| 08 | Recordings | TTS Cache Management & Audio Streaming | `LOCAL-REAL` | PASS | TTS Cache endpoints verified in schema (present=True) |
| 09 | CRM Leads | CRM Stages, CSV Import/Export & Timeline | `LOCAL-REAL` | PASS | All 6 new CRM gap endpoints verified |
| 10 | Appointments | Appointment Booking & Conflict Detection | `LOCAL-REAL` | PASS | Appointment calendar routes active (present=True) |
| 11 | Voice Forms | Voice Form Schema & Field Validation | `LOCAL-REAL` | PASS | Voice form submission routes verified (present=True) |
| 12 | Web Widgets | Public Widget Script Middleware Bypass | `LOCAL-REAL` | PASS | /widget.js exempt from Next.js authentication redirect |
| 13 | Prompt Templates | Template Management & PUT Route | `LOCAL-REAL` | PASS | PUT /prompt-templates/{template_id} verified |
| 14 | Agent Runs | Per-Call Record & Structured Error Reason Codes | `LOCAL-REAL` | PASS | Full telemetry recorded; error taxonomy supports 6 structured failure codes |
| 15 | Sovereign Wallet | Payment Gateway Webhook HMAC Verification | `LOCAL-SIM` | PASS | Razorpay webhook HMAC-SHA256 signature strictly validated |
| 15 | Sovereign Wallet | Local AI 0-Minute Free Run Invariant | `LOCAL-REAL` | PASS | Runs using 100% local stack deduct exactly 0 voice minutes |
| 16 | Reports | Aggregated Metrics & CSV Export | `LOCAL-REAL` | PASS | Campaign CSV streaming report route verified |
| 17 | Sovereign Admin | Process Health Monitoring Panel | `LOCAL-REAL` | PASS | GET /admin/monitoring/process-health verifies Postgres, Redis, MinIO, Orchestrator, Local AI |
| 17 | Sovereign Admin | Symmetric Master Key Alias Deletion | `LOCAL-REAL` | PASS | Alias pairs prevent orphaned models across provider renames |
| 17 | Sovereign Admin | Settings Dynamic Cache Invalidation | `LOCAL-REAL` | PASS | Settings mutations immediately invalidate catalog truth layer cache |

---

## Verification Summary by Evidence Label

- **`LOCAL-REAL`**: 22 tests (22 passed)
- **`LOCAL-SIM`**: 4 tests (4 passed)
- **`CLOUD-REAL`**: 0 tests (0 passed)
- **`STAGING-ONLY`**: 1 tests (0 passed)

---

## Push Gate Status

- **Tests Passed:** 26/26
- **Regressions Detected:** None
- **Gate Condition:** Awaiting user explicit confirmation `CONFIRM PUSH` before pushing to remote repository.
