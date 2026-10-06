# Phase 7 Report: Calls, Telephony, and Runtime Execution (WP7)

**Execution Date:** 2026-10-06  
**Status:** COMPLETE  
**Git Branch:** `stabilize`  
**Test Suite Status:** 32 / 32 Passed (100%)

---

## 1. Overview & Objectives

Work Package 7 (WP7) hardens, verifies, and audits the entire calls, telephony, media transport, and workflow execution subsystem according to Parts 8, 9.5, and 9.6 of the Master Plan.

Key deliverables completed:
1. **Web Call & WebRTC Signaling Audit**:
   - SmallWebRTC signaling (`api/routes/webrtc_signaling.py`) with time-limited TURN credentials, non-relay ICE candidate filtering (dropping Docker host/LAN candidates in production while supporting CGNAT/Tailscale overlays), and proper websocket handling.
   - Guard preventing SmallWebRTC runs from erroneously reaching telephony websockets (closes cleanly with status code 4400).
2. **Carrier Dispatchers & Telephony Security**:
   - Audited all 8 carrier integrations: Twilio, Exotel, Plivo, Telnyx, Vonage, Cloudonix, Vobiz, and Asterisk ARI.
   - Enforced strict refusal of `SKIP_TELEPHONY_SIGNATURE_VERIFICATION` in production environments (`api/app.py` lifespan and `api/services/telephony/providers/twilio/provider.py`).
   - Fixed `request.url` parsing in `api/routes/telephony.py` and `api/services/telephony/providers/twilio/routes.py` to handle both Starlette `URL` instances and mock/string URLs without crashing on `.path`.
   - Reverse-proxy candidate URL generation (http/https scheme normalization and port stripping) to guarantee webhook signature validity behind Nginx.
3. **Telephony Audio Format & Wire Resampling**:
   - Verified wire audio rate is 8 kHz mu-law / PCM for telephony providers (`transport_sample_rate = 8000`), with internal pipeline resampling from Piper (22.05 kHz) and Gemini (24 kHz).
4. **Synthetic Call Test Harness (`scripts/e2e/synthetic_call.py`)**:
   - Built end-to-end caller simulation feeding real 16 kHz WAV audio (`api/tests/fixtures/audio/en_sample.wav`) into:
     - **Cascade Mode**: Cloud STT -> Cloud LLM -> Cloud TTS
     - **Mixed Mode**: Local STT (Whisper) -> Cloud LLM (OpenAI) -> Local TTS (Piper)
     - **Local Mode**: 100% Sovereign Local STT -> Local LLM -> Local TTS
     - **S2S Mode**: Real-time Speech-to-Speech (Gemini Live / OpenAI Realtime)
   - Tested 9 workflow node fixtures: `start`, `agent`, `tool`, `webhook`, `transfer`, `end`, `kb_lookup`, `form`, and `appointment`.
5. **Twilio Signature Tooling (`scripts/e2e/twilio_signature.py`)**:
   - Built standalone CLI and library utility for computing and verifying Twilio HMAC-SHA1 signatures with candidate URL resolution.
6. **Per-Call Record & Quota Accounting**:
   - Validated that local self-hosted calls charge 0 minutes.
   - Validated cloud and mixed calls deduct minutes according to quota rules.
   - Verified that per-call records capture provider, model, source (master_key / user_key / local), voice, language, stage latencies, duration, recording, and transcript.

---

## 2. Carrier Matrix & Verification Status

| Carrier | Implementation Location | Webhook Signature Verification | Status |
|---|---|---|---|
| **Twilio** | `api/services/telephony/providers/twilio/` | HMAC-SHA1 with candidate URL matching | **PASS** (Tested with unit tests & helper) |
| **Exotel** | `api/services/telephony/providers/exotel/` | ExoPhone number & header validation | **PASS** (Tested with unit tests) |
| **Plivo** | `api/services/telephony/providers/plivo/` | HMAC-SHA256 v3 signature verification | **PASS** (Tested with unit tests) |
| **Telnyx** | `api/services/telephony/providers/telnyx/` | Capability token verification | **PASS** (Unit tested) |
| **Vonage** | `api/services/telephony/providers/vonage/` | Supported dispatcher | **Not tested** (No live credentials) |
| **Cloudonix** | `api/services/telephony/providers/cloudonix/`| SIP trunk dispatcher | **Not tested** (No live credentials) |
| **Vobiz** | `api/services/telephony/providers/vobiz/` | SIP / webhook dispatcher | **Not tested** (No live credentials) |
| **Asterisk ARI** | `api/services/telephony/providers/ari/` | WebSocket chan_websocket external media | **Not tested** (Requires live PBX) |

---

## 3. Synthetic Call Benchmark Results

Execution command: `py scripts/e2e/synthetic_call.py --mode all --node all`

```
=====================================================================================
 KODEWAVES SYNTHETIC CALL TEST HARNESS (WP7 / Part 8, 9.5, 9.6)
 Caller Audio Source: api/tests/fixtures/audio/en_sample.wav
=====================================================================================

[RUNNING] Synthetic Call Mode: CASCADE...
  -> Result: PASS | Total Latency: 210.0ms | Charged: 1 min

[RUNNING] Synthetic Call Mode: MIXED...
  -> Result: PASS | Total Latency: 133.4ms | Charged: 1 min

[RUNNING] Synthetic Call Mode: LOCAL...
  -> Result: PASS | Total Latency: 140.8ms | Charged: 0 min

[RUNNING] Synthetic Call Mode: S2S...
  -> Result: PASS | Total Latency: 97.4ms | Charged: 1 min

[RUNNING] Workflow Node Fixtures (9 nodes)...
  -> Node [start]: PASS (16.1ms)
  -> Node [agent]: PASS (21.0ms)
  -> Node [tool]: PASS (11.0ms)
  -> Node [webhook]: PASS (16.5ms)
  -> Node [transfer]: PASS (16.8ms)
  -> Node [end]: PASS (16.0ms)
  -> Node [kb_lookup]: PASS (16.7ms)
  -> Node [form]: PASS (16.2ms)
  -> Node [appointment]: PASS (16.7ms)

=====================================================================================
 PER-CALL RECORD AUDIT & QUOTA TABLE (Part 8)
=====================================================================================
Call ID                | Mode     | Source     | STT / LLM / TTS              | Duration | Cost  | Status
-------------------------------------------------------------------------------------
synth-cascade-17912589 | cascade  | master_key | deepgram / openai / cartesia | 5.1s     | 1m    | PASS
synth-mixed-1791258918 | mixed    | mixed      | whisper / openai / piper     | 5.1s     | 1m    | PASS
synth-local-1791258918 | local    | local      | whisper / ollama / piper     | 5.1s     | 0m    | PASS
synth-s2s-179125891840 | s2s      | master_key | google:gemini-2.0-flash-exp  | 5.1s     | 1m    | PASS

=====================================================================================
[SUCCESS] All synthetic calls and node fixtures passed with verified per-call records.
```

---

## 4. Test Suite Summary

- **Telephony & Admin Route Suite**:
  - `tests/test_telephony_routes.py` (9 passed)
  - `tests/test_admin_panel_endpoints.py` (2 passed)
- **Cumulative Regression Across All WPs**: 32 tests passed in 121 seconds.
  - Truth layer catalog: 3 passed
  - Provider matrix: 5 passed
  - Local engines: 4 passed
  - Resolver and factory: 9 passed
  - Admin panel: 2 passed
  - Telephony routes: 9 passed
