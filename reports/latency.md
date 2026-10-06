# Kodewaves Latency and Concurrency Report

**Date:** October 2026  
**Environment:** Staging / Local Preflight  
**Platform:** Sovereign Voice AI Pipeline  

## 1. Executive Summary

> [!WARNING]
> **DRY RUN ONLY — NOT A MEASUREMENT.**  
> Latency against real providers will be measured in staging with real keys.  
> Zero latency numbers are reported until measured against live provider endpoints and local daemons.

- **Dry-run Harness:** `scripts/e2e/synthetic_call_dryrun.py` and `scripts/e2e/loadtest_dryrun.py` execute flow topologies in test/mock mode to verify concurrency counters, pipeline coordination, and wallet invariants.
- **Real-Measurement Harness:** `scripts/e2e/live_check.py` is configured for live latency measurement once API keys and local daemons are provisioned on staging.
- **Sentence Streaming:** LLM tokens stream into TTS sentence aggregator; first audio emitted as soon as initial clause/sentence is formed.
- **VAD & Endpointing:** Tuned to Silero VAD stop threshold 500ms, Deepgram STT endpointing 300ms, server-side VAD for Realtime S2S.
- **Sovereign Local Quota Invariant:** Verified in test suite `api/tests/test_billing_invariants.py` that 100% self-hosted CPU calls deduct 0 minutes from tenant wallets.

## 2. Benchmark Status Matrix

| Setup | Concurrency | Success Rate | Mean STT (ms) | Mean TTFT (ms) | Mean TTFB (ms) | Mean Total (ms) | Status |
|---|---|---|---|---|---|---|---|
| Cascade (Deepgram + GPT-4o-mini + Cartesia) | 1, 3, 5, 10 | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED (no cloud keys) |
| Mixed (Whisper + GPT-4o-mini + Piper) | 1, 3, 5, 10 | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED (no local daemon / keys) |
| Local (Whisper + Ollama + Piper) | 1, 3, 5, 10 | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED (no local daemons running) |
| S2S (Gemini Live / OpenAI Realtime) | 1, 3, 5, 10 | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED (no cloud keys) |

## 3. Real Latency Measurement Plan for Staging

To capture actual millisecond latency on staging:
1. Provision upstream API credentials or local AI daemons in the staging environment.
2. Run `python scripts/e2e/live_check.py`.
3. Record real HTTP / WebSocket round-trip times and append raw command outputs.

## 4. Default Capacity Caps Enforced in Code

| Parameter | Admin Configurable | Default Value | Recommended Safe Production Cap |
|---|---|---|---|
| `default_org_concurrency_limit` | Yes (Platform Settings) | 10 calls | 10 - 25 calls per tenant |
| `max_concurrent_calls` | Yes (Platform Settings) | 50 calls | 50 - 100 calls platform-wide |
| `local_ai_max_concurrency` | Yes (Local AI Settings) | 2 calls | 2 - 4 calls per 4-core VPS |
| `FASTAPI_WORKERS` | Auto (calculated from CPU) | max(1, min(CPU, 4)) | 1 - 4 uvicorn workers |
| `vad_stop_secs` | Workflow Run Config | 0.5s (500ms) | 400ms - 600ms |
| `deepgram_endpointing` | Pipeline Factory | 300ms | 300ms |
