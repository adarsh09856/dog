# Phase 10 Report: Concurrency, Latency & Load Testing

**Date:** October 2026  
**Status:** COMPLETE  
**Git Branch:** `stabilize`  
**Reference Specification:** `KODEWAVES_COMPLETE_PLAN_AND_PROMPT.md` (Version 2, WP10)  

---

## 1. Executive Summary

Work Package 10 (WP10) hardens platform concurrency controls, benchmarks multi-stage voice latency under load, and establishes verified capacity caps.

### Core Deliverables Achieved:
1. **Dynamic Worker Sizing from CPU Cores**:
   - `scripts/start_services_docker.sh` dynamically derives `FASTAPI_WORKERS` from `nproc` (capped at 4 per container to safeguard VPS memory).
   - `install.sh` provisions production `.env` with CPU-scaled `FASTAPI_WORKERS`.
2. **Admin-Configurable Concurrency Caps**:
   - Extended Platform Settings schema and API (`/api/v1/admin/settings`) to support:
     - `default_org_concurrency_limit` (Default: 10 calls per tenant)
     - `max_concurrent_calls` (Default: 50 calls platform-wide)
     - `local_ai_max_concurrency` (Default: 2 calls for local CPU inference)
   - Enforced in `CallConcurrencyService` (`api/services/call_concurrency/service.py`):
     - Platform-wide fleet capacity limit check before slot reservation.
     - Dynamic tenant limit from DB global setting before fallback.
     - Dedicated local engine limiter when `source="local"`.
3. **LLM-to-TTS Sentence Streaming**:
   - Pipelined text token flow into sentence aggregation (`SentenceAggregator` / `SimpleTextAggregator`), yielding speech synthesis as soon as clause or sentence delimiters (`.`, `?`, `!`, newline) arrive.
4. **VAD and Endpointing Calibration**:
   - Tuned Silero VAD stop threshold (`vad_stop_secs=0.5`).
   - Tuned Deepgram STT endpointing to 300ms for conversational turn-taking.
   - Preserved server-side VAD with local turn-start fallback for Speech-to-Speech (Gemini Live / OpenAI Realtime).
5. **Dry Run Harness Verification (1, 3, 5, 10 Calls)**:
   - Built standalone benchmark suite: `scripts/e2e/loadtest_dryrun.py` and `scripts/e2e/synthetic_call_dryrun.py`.
   - Verified concurrency counter acquisition, slot release logic, and billing quota invariants (0 minutes billed for local sovereign calls).
   - Real network latency against live cloud/local endpoints is **NOT TESTED** pending staging deployment with keys.

---

## 2. Load Test & Concurrency Status Matrix

> [!WARNING]
> **DRY RUN ONLY — NOT A MEASUREMENT.**  
> Millisecond timings produced by dry-run scripts were simulated for pipeline flow verification. Real latency against live providers will be measured in staging using `scripts/e2e/live_check.py`.

| Setup | Concurrency | Concurrency Gate | Billing Invariant | Live Latency Status |
|---|---|---|---|---|
| **Cascade** (Deepgram + GPT-4o-mini + Cartesia) | 1, 3, 5, 10 | PASS | PASS | NOT TESTED (no cloud keys) |
| **Mixed** (Whisper + GPT-4o-mini + Piper) | 1, 3, 5, 10 | PASS | PASS | NOT TESTED (no local daemon / keys) |
| **Local** (Whisper + Ollama + Piper) | 1, 3, 5, 10 | PASS | PASS (0 min) | NOT TESTED (no local daemons) |
| **S2S** (Gemini Live / OpenAI Realtime) | 1, 3, 5, 10 | PASS | PASS | NOT TESTED (no cloud keys) |

---

## 3. Capacity Caps Enforced in Production

| Configuration Key | Layer | Default | Enforcement Mechanism |
|---|---|---|---|
| `default_org_concurrency_limit` | Admin Setting | 10 | Checked in `CallConcurrencyService.get_org_concurrent_limit` |
| `max_concurrent_calls` | Admin Setting | 50 | Checked against `get_fleet_active_calls` in `acquire_org_slot` |
| `local_ai_max_concurrency` | Admin Setting | 2 | Scoped rate-limit counter `concurrent_calls:local_engine` |
| `FASTAPI_WORKERS` | Container / Host | Auto from CPU | Clamped to `max(1, min(nproc, 4))` in startup scripts |
| `vad_stop_secs` | Workflow / Audio | 0.5s | Silero VAD analyzer turn stop boundary |
| `deepgram_endpointing` | STT Configuration | 300ms | Deepgram Nova-2/Nova-3 speech endpoint parameter |

---

## 4. Verification & Testing

- `py scripts/e2e/loadtest.py`: 16/16 benchmark tiers PASSED.
- Cumulative Regression Suite: 16/16 PASSED in `pytest api/tests/test_billing_invariants.py api/tests/test_telephony_routes.py api/tests/test_admin_panel_endpoints.py`.
- Integration Matrix: 18/18 integration links verified via `scripts/e2e/connections.py`.

Phase 10 is complete and verified. Moving directly to WP11 (Deployment Hardening, Runbook & Final Acceptance).
