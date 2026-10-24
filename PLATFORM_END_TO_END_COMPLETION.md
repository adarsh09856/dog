# Kodewaves end-to-end completion tracker

Updated: 24 October 2026. Scope: the original full-platform request plus the current self-hosted voice priority. This is a live checklist, not a claim that the platform is complete.

Commercial client installation, owner control, code integrity, domain/IP binding and the full theme/public-site change are planned separately in `CLIENT_BUNDLE_SUPERADMIN_PLAN.md`. They remain open.

## Status rules

- **Verified live**: deployed and exercised through the real user journey, with saved result and failure handling checked.
- **Code verified**: implementation or automated test passed, but the live journey remains untested.
- **Open**: a known failure, missing implementation, or missing acceptance evidence.
- Each completed row must link to the commit/file, test result, deployment and run/action evidence. Do not turn an old audit finding into a current defect without rechecking it.

## 1. Setup, accounts and agent creation

| Journey | Current evidence / status | Acceptance still needed |
|---|---|---|
| Sign in, organization selection, roles and tenant boundaries | Open for full journey | Test authorized and forbidden navigation/API actions across two workspaces. |
| Agent list, create from every template, custom agent, edit, save, reload | Open for full journey | Check UI state, persistence, validation and recovery on each template. |
| Workflow nodes, prompts, tool attachments, draft, publish, version restore | Open for full journey | Publish and run each representative agent; verify saved version and tool scope. |
| Model, language, voice and provider settings | Partial code/UI checks; full journey open | Verify selected model/voice is the actual runtime model, including BYOK and managed/local modes. |
| Model catalog and admin model controls | Static catalog audit in `reports/platform-audit/model-route-static-audit.md` | Resolve wrong LLM roles, legacy aliases and UNTESTED presentation; verify supported model/provider routes. |

## 2. Self-hosted browser conversation — current priority

| Journey | Current evidence / status | Acceptance still needed |
|---|---|---|
| Browser connection and microphone lifecycle | Open | Fresh real-microphone call; verify reconnect, consent and no early mic shutdown. Browser automation currently blocked by Work settings. |
| Hindi, English and Hinglish STT | Partial live evidence | Names, numbers, dates, code switching and short follow-ups across agent types. |
| LLM context, relevance and language switch | **Failed live**: Workflow 22 run 402 repeated the same wrong name request after correct STT, and ignored the English request | Fix shared context/history handling; repeat multi-turn test across template types without canned answers. |
| LLM latency | **Failed target**: run 402 first token 5.859/1.230/0.999 s; first audio 8.486/6.288/3.462 s | Measure speech end to first audible sample for cold and follow-up turns; target 1–1.5 s where feasible, disclose any unmet cases. |
| TTS streaming, completion and interruption | Open; run 399/402 indicate gaps/cancellation risks | Trace first/last PCM, client playback, gaps, cancellation and barge-in; prove no mid-sentence cut or stale overlap. |
| Browser Test Workflow text chat | API reply-boundary fix deployed; 409 session-version recovery in progress in linked chat | Test failed send, retry and visible reply after UI deployment. |
| Tool-backed agent action | Open | Prove booking or other action is called, persisted and reported only after success; no invented outcome. |

## 3. Telephone and campaign journeys

| Journey | Current evidence / status | Acceptance still needed |
|---|---|---|
| Twilio inbound routing from +1 350 900 1419 | Open | Real PSTN inbound call, correct workflow, media, transcript, recording and end state. |
| Twilio outbound to authorized 6366458170 | Prior runs failed accuracy/latency; next call pending browser gate | One call after browser acceptance; Hindi/English/Hinglish, no repetition/cut/overlap, answer and greeting delay. |
| Carrier announcement and first greeting | Prior run 390 measured startup stages; reported 3–4 s announcement | Distinguish carrier timing from platform connection and greeting delivery; optimize measured platform portion. |
| Campaign create, preflight, queue, launch, pause, retry, stop | Open | Real queue effects, contacts, opt-out, failure recovery and billing reconciliation. |
| Concurrent calls and capacity limits | Open | Verify queue/admission, CPU saturation, rejection and recovery without audio degradation. |

## 4. CRM, scheduling and integration

| Journey | Current evidence / status | Acceptance still needed |
|---|---|---|
| Contact import/create/edit/search, workspace switching | Partial code checks; open live | Persistence, stale request protection and cross-workspace isolation. |
| Appointment booking, conflict checks, edit and cancel | API tests and isolated DB concurrency test passed historically; live agent journey failed earlier | Real agent tool call, persisted ID, correct dates/timezone, no invented booking. |
| Post-call CRM outcome, transcript, recording and follow-up | Open | Verify run association, contact timeline, campaign outcome and failure recovery. |
| Forms, widgets and embed protocol | Open | Real public submission, active/schema enforcement, tenant routing and UI display. |

## 5. User and admin panels

| Journey | Current evidence / status | Acceptance still needed |
|---|---|---|
| Every user page and action | Historical route/page inventories exist; not live acceptance | Open, create/edit/delete where applicable, reload, error and authorization checks. |
| Every admin page and action | Some plans, credit bundles, moderation UI fixes are local/code verified | Deploy and test saved state, zero values, retry errors, role gating and backend effect. |
| Plans, bundles, wallet, usage and payments | Open; historical audit found contract/accounting gaps | Verify product controls persist, checkout/webhook integrity, wallet idempotency and correct usage. |
| Provider settings, credentials and catalog health | Open full journey | Verify UI values match actual resolver/service and statuses do not overstate success. No key-based model probes unless user asks. |
| Logs, monitoring, audit and exports | Open | Trace real actions and failures end to end; verify downloads, redaction and tenant scope. |
| Public Kodewaves theme and Dograh visual cleanup | In progress: public home/pricing copy now avoids fixed savings, outdated model and small-server guarantees; focused pricing test passes locally. Visual rebuild remains open. | Replace public/auth/user/admin visual remnants, ensure responsive light/dark design and truthful product copy; verify live deployment. |
| Client installation and owner-only superadmin | Open | Deliver client-only bundle, owner-issued license, domain/installation binding, optional IP policy and enforced feature grants. |
| Signed release and modification alert | Open | Verify protected component changes, notify owner and handle new-action gating safely; allow approved client branding changes. |

## 6. Security, release and acceptance

| Journey | Current evidence / status | Acceptance still needed |
|---|---|---|
| Historic audit findings F01–F35 | See `reports/audit-2026-10-07/REPORT.md`; individual current states unreviewed here | Recheck each against current source and production; link fix or evidence, never assume old status. |
| Production source and deployment reconciliation | Open | Compare active worktrees, VPS source and running image; deploy coherent build with rollback. |
| Regression tests and health | Partial focused suites and service health have passed | Run relevant backend/UI tests, typecheck/build, inspect deployed health and run evidence. |
| Browser acceptance | Open | Real audio acceptance for representative templates and languages. |
| Telephone acceptance | Open | PSTN inbound and authorized outbound after browser acceptance. |

## Next handoff

The linked chat `Audit end-to-end platform flows` owns the active shared self-hosted voice and UI fixes. It should update this tracker (or return a reconciled equivalent) with exact file/commit, tests, deploy state and live run IDs for every completed item. Complete the current voice batch first, then work through the remaining UI and platform rows. This tracker is open in the current chat for review.
