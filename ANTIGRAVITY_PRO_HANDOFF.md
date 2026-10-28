# Kodewaves: complete platform delivery handoff

**Snapshot:** 20 October 2026. **Repository:** `E:\ai\aagent\newai` (branch `stabilize`, HEAD `b45d766a` when this file was prepared). This is an execution brief, not a completion certificate. Recheck the worktree and production state before acting; both can change independently.

**Reading order:** sections 1–8 explain the target and architecture; sections 9–12 provide the tools, detailed T00–T21 tasks and execution method; section 13 is the newest measured state and exact resumption point. Give the receiving agent this entire file, not only the short prompt.

## 1. Product target

Deliver a configurable, independently branded, multi-tenant voice AI platform that a new customer can install on their own VPS, set to India/IST by default, configure without confusing questions, and use for many services beyond appointment booking. A regular user can create or customize an agent, select permitted model/voice/language options, test text and audio, publish, connect web and telephone channels, run campaigns, and inspect the resulting records and charges. An administrator can manage capabilities, credentials, prices, users, monitoring, and deployment settings without exposing admin functions to regular users.

The first priority is a **CPU-only, self-hosted** conversational path. It must preserve what the caller actually said, understand follow-ups, answer in the caller's language, use connected tools for real actions, avoid invented results, and speak clearly with stable, appropriate voice and grammar. The requested target is **700–800 ms from end of user speech to first intelligible audio**. Treat that as an acceptance target to measure under stated hardware and concurrency, never as an assumed property. If the 4-core VPS cannot meet it without sacrificing accuracy or voice quality, demonstrate the limit and specify the smallest hardware/model change that does.

Language coverage means all 22 scheduled Indian languages: Assamese, Bengali, Bodo, Dogri, Gujarati, Hindi, Kannada, Kashmiri, Konkani, Maithili, Malayalam, Manipuri, Marathi, Nepali, Odia, Punjabi, Sanskrit, Santali, Sindhi, Tamil, Telugu, and Urdu; also Indian-accented English and realistic code-switching. For **each language**, prove STT, LLM answer quality, TTS voice, female/male (or honestly unavailable) choices, script handling, web audio, and telephone audio separately. Never label a language usable solely because a model card lists it.

## 2. Architecture and data flow

```text
Next.js 15 / React 19 UI (ui/src/app, generated client)
  -> FastAPI routes (api/routes, /api/v1)
  -> organization-scoped DB clients (api/db) -> PostgreSQL
  -> domain services / ARQ tasks -> Redis
  -> call engine (api/services/workflow + api/services/pipecat)
  -> Pipecat pipeline (pipecat submodule)
       web: WebRTC + Coturn       phone: provider webhooks/media
       audio -> VAD -> STT -> turn/context -> LLM/tools -> TTS -> audio
  -> recordings/transcripts/files -> MinIO
  -> run, usage, billing, CRM, report and campaign state -> PostgreSQL
```

Important implementation locations:

| Concern | Read/trace from |
|---|---|
| Runtime graph, prompts, tools, call state | `api/services/workflow/`, especially `pipecat_engine.py` and `pipecat_engine_context_composer.py` |
| Web/phone speech pipeline, VAD, turn boundaries, voice services | `api/services/pipecat/run_pipeline.py`, `speaches_stt.py`, `speaches_tts.py`, `local_speech_aggregator.py`, `call_monitor_processor.py` |
| Model catalog, defaults, provider construction | `api/services/configuration/`, `api/services/catalog/`, `api/services/pipecat/service_factory.py` |
| Self-hosted speech adapters | `api/local_models/indic_stt/`, `indic_vits/`, `indus_tts/`, `indic_mio/` |
| Telephone providers, callbacks and media | `api/services/telephony/` and its provider packages |
| UI and API contract | `ui/src/app/`, `ui/src/components/`, `ui/src/client/`, `ui/src/lib/` |
| Jobs, storage, schema and migrations | `api/tasks/`, `api/db/`, `api/alembic/`, Compose files |

The deployed VPS has **4 CPU cores, 15 GiB RAM, and a 193 GiB root filesystem** (120 GiB free at this snapshot). The live stack included healthy UI, API, Ollama, IndicConformer STT, regional VITS TTS, Indus TTS, PostgreSQL, Redis and MinIO; Coturn was running. A healthy container proves readiness of that process, not a successful conversation. The user's requested cleanup of Indus and unused images/models is still subject to dependency/selection checks before removal. Preserve unrelated sites on the same VPS.

## 3. What the current evidence actually says

- The current local production conversation model was `qwen3.5:2b` through Ollama. The workflow used IndicConformer CTC INT8 for explicitly chosen Kannada and `indic-vits-rasa-13` for Kannada TTS. Do not assume IndicConformer auto-detects languages. The regional VITS catalog covers 13 documented languages, **not all 22**. Indus was still running for Hindi/English at the snapshot. DhVaani-0.5 is a candidate: the account had been granted access, but an authenticated server download, CPU benchmark, listening comparison, licensing review and integration were not complete. Do not claim it is installed or accepted.
- The user's WebRTC run **#263** on workflow **19**, draft definition **#37**, had a Kannada greeting and a caller asking about an order. STT requests were about 0.7 seconds, but Qwen first-token waits were roughly 11–13 seconds, with regional TTS sometimes another 4 seconds. The visible response delay was **22.397 seconds** and the answer wrongly implied it could check an order. STT requests at 07:24:23, 07:24:43 and 07:24:59 UTC show the caller spoke again while waiting; do not assume those were one contiguous utterance. Trace turn start/stop and interruption events before editing segmentation.
- The existing workflow 19 draft had a stale template instruction promising to record/pass order details without a connected tool. A backup was taken in the API container and only draft #37 was corrected. A two-turn synthetic WebRTC retest no longer claimed a check or recording, but first audible replies still took **27.4 seconds and 16.2 seconds**, and Kannada was poor. The published definition #35 and other saved custom prompts were not silently rewritten.
- Prior comparisons rejected `qwen3:4b` (internal-looking reasoning and long output) and `qwen3.5:4b-q4_K_M` (better isolated wording but 33.4/24.8-second WebRTC first audio and false action claims). They were removed. Focused component tests and health checks exist, but **no complete self-hosted web/telephone acceptance, all-language acoustic acceptance, or full-platform page acceptance has been established**.
- The status and historical evidence are in `IMPLEMENTATION_STATUS.md` and `PAGE_ACCEPTANCE.md`. Older dated entries describe earlier deployments or candidate models, not necessarily the current selection. Reproduce current facts before a new fix. Existing source has many modified and untracked files; preserve and inspect all of them.

## 4. Required end-to-end journeys

For every route below, exercise **every visible control and section**, including dialogs, filters, empty states, error states, validation, reload persistence, permissions, background effects and cross-page synchronization. Test as a fresh regular user, workspace admin, platform admin, and a second tenant where applicable. A page rendering successfully does not pass.

| Area | Routes and acceptance focus |
|---|---|
| Overview | `/overview`: accurate KPIs, source data, filters, links, tenant scope |
| Voice Agents | `/workflow`, `/workflow/create`, `/workflow/[id]`, settings/runs: template and custom create, edit, test text/audio, publish, versioning, language/voice/model persistence, tools, delete/archive |
| Campaigns | `/campaigns` and create/detail/edit: contacts, schedule, preflight, retries, capacity, stop/resume, results, billing |
| Models | `/model-configurations`, `/admin/models`: permitted/installed selection, self-hosted readiness, exact STT/LLM/TTS/voice/language route, catalog synchronization and honest errors |
| Telephony | `/telephony-configurations` and detail: credentials, number assignment, inbound/outbound, signed callbacks, greeting, follow-up, transfers, hangup, recordings |
| Tools | `/tools` and detail: definitions, authentication, invocation, error/result grounding, tenant isolation |
| Files and Recordings | `/files`, `/recordings`: upload, processing, search, scoped retrieval, playback, download, deletion and storage state |
| CRM and Appointments | `/crm`, `/appointments`: CRUD, deduplication, tool writeback, dates in IST, consent and scope |
| Voice Forms and Widgets | `/forms`, `/widgets`: creation, publish/embed, submission, identity, agent selection, persistence and error handling |
| Prompt Templates | `/prompt-templates`: selection, generation, editing, creation of functional multi-service agents, no fictional tools |
| Runs and Reports | `/usage`, `/reports`, workflow run details: transcripts, timing, model/source attribution, actions, analytics and exports match raw events |
| Billing | `/billing-sovereign` and admin billing pages: wallet, rates, payments, replay/concurrency protection, actual source charges and reconciliation |
| Administration | `/admin` plus users, settings, plans, monitoring, moderation, audit logs: real actions, role checks, capability propagation, no admin exposure to ordinary users |
| Installation/identity | login/signup/settings and deployment: region/brand configuration, startup/restart, migrations, secret handling, multi-tenant isolation |

Add any newly discovered routes, side panels, contextual actions, public APIs, webhooks and workers to `PAGE_ACCEPTANCE.md`; this table is a starting map, not a scope cap.

## 5. Working method: understand every relevant line, then change and prove

1. **Inventory first.** Read root, `api/`, `ui/` and telephony `AGENTS.md`; capture `git status`, diff, current commit/submodule state and deployment configuration. Do not reset or overwrite existing edits. Classify tracked/untracked source, tests, migrations, scripts, docs, generated clients, lockfiles and binaries. Review human-authored files line by line in bounded chunks; record each file's review status and hash/revision. Generated files and model weights need generator/integrity checks, not a claim of manual line review.
2. **Map each action.** For every page element, trace `UI control -> generated/client request -> route -> auth/organization -> service -> DB transaction or worker -> external provider -> UI feedback`. Record the exact input fields, defaults, validation, side effects, errors, and persisted output. Review both successful and failure branches. Cross-check saved draft, published definition, campaign snapshot and runtime resolved config; never assume they are the same.
3. **Reproduce a defect with the actual configuration.** Capture a fresh run ID and immutable definition/version/model/voice/language, source audio and transcript (with private data redacted), timing by stage, resource load and logs. Use one variable change at a time, with baseline and after measurements. Synthetic requests, direct model calls, browser calls and telephone calls are different evidence classes.
4. **Fix the owning layer.** Keep route handlers for HTTP/auth concerns; use `api/db` for SQL/transactions and domain services for reusable behavior. Regenerate the UI client from OpenAPI if contracts change. Keep cross-worker settings synchronized through the repository's worker-sync mechanism. Preserve exact provider/model/credential source and billing attribution; do not silently swap cloud and local.
5. **Test at the right level.** Use focused regression tests for the actual defect, then relevant backend/unit/contract/database tests, UI tests and TypeScript/build. Backend database tests must load `api/.env.test` and prove test DB isolation before writing. Do not use production credentials for automated DB tests. Perform authenticated live browser journeys and authorized telephone tests with a designated test number only. Never call customers or run paid campaigns as diagnostics.
6. **Verify speech with real acceptance data.** Prepare consented native-speaker utterances for all 22 languages, Indian English and code-switching; include different microphones, noise and telephone codecs. Measure STT correctness/script, LLM answer/tool grounding, TTS intelligibility/naturalness/pronunciation/voice identity, interruption recovery, cut words and pause gaps. Record p50/p95/p99 end-of-speech-to-first-audio and whole-answer times for warm/cold, one call and concurrent calls. Check CPU, RAM and storage during the exact run. A 700–800 ms claim needs a representative passing distribution, not one short clip.
7. **Deploy narrowly, compare, and roll back failures.** Snapshot the relevant configuration and DB state, build only the affected service, verify container and public health, confirm the exact source/image/model in the live call, then rerun the same scenario. Avoid broad Docker or filesystem pruning. Remove a model/image/cache only after proving no active container, saved agent, fallback or deployment references it; record space reclaimed and restore path. Leave unrelated VPS sites untouched.
8. **Maintain an evidence ledger.** Each row: requirement, code/route, before/after behavior, test command/result, live run ID, p50/p95 if performance-related, current status (`passed`, `failed`, `blocked`, `unverified`), date, and next action. Update `IMPLEMENTATION_STATUS.md` and `PAGE_ACCEPTANCE.md`. A passing component test must never close a broader journey.

## 6. Delivery order and exit gates

| Gate | Required proof before moving status to passed |
|---|---|
| A. Reproducible baseline | Clean documented startup, isolated test DB, migrations, healthy dependencies, two-tenant fixtures, source/deployment inventory |
| B. Self-hosted model qualification | Per-language installed STT/LLM/TTS inventory, licenses/access, CPU/RAM/latency and human listening comparisons; remove unfit models only after dependency audit |
| C. Conversation path | Accurate greeting and at least three grounded follow-ups per service scenario in text, WebRTC and telephone; no repeated greeting, invented action, empty response or cut audio; measured latency distribution |
| D. Configuration fidelity | User selections survive draft/edit/publish/test/run/campaign/widget/phone; admin toggles and provider credentials propagate; tenant and role boundaries hold |
| E. Product journeys | Every area in section 4 and every discovered action passes authenticated live and regression checks, including error/empty/permission cases |
| F. Operations | Billing reconciliation, restart/recovery, storage cleanup, monitoring, safe installation/branding/region, documented capacity and backup/restore |

Do not call the platform production-ready until **all** gates pass on the intended deployment. If hardware, model access or language data prevents a gate, keep its status failed/blocked with exact evidence while continuing independent work.

## 7. Copy/paste execution prompt for Antigravity Pro

> Work in `E:\ai\aagent\newai`. Read `ANTIGRAVITY_PRO_HANDOFF.md`, applicable `AGENTS.md`, `IMPLEMENTATION_STATUS.md`, `PAGE_ACCEPTANCE.md`, the current git diff, and the live deployment state first. The objective is the entire Kodewaves platform described in the handoff, not just booking or one workflow. Preserve our independent branding, self-hosted changes, all existing edits, and unrelated VPS sites. Never commit/push tests, diagnostics or reports to GitHub; never place secrets in source/output. Do not claim completion from tests or container health alone.
>
> Prioritize the self-hosted speech flow. Reproduce workflow 19's currently failing text/WebRTC call using its **actual saved draft or published definition**, capture run ID and stage timing, then fix the earliest measured bottleneck or incorrect behavior in the owning layer. The last measured run #263 took 22.397 seconds and falsely implied an order lookup; a draft prompt correction stopped that claim but a synthetic retest still took 27.4/16.2 seconds with poor Kannada. Validate any STT/LLM/TTS replacement on the 4-core VPS before promoting it. Prove language coverage individually for all 22 scheduled Indian languages plus Indian English/code-switching; do not hardcode Hindi/English or invent auto-detection. Require appropriate voice/gender grammar, intelligible non-clipped speech, grounded follow-ups and measured end-of-speech-to-first-audio latency. If 700–800 ms is infeasible on this hardware, report an evidence-backed hardware/model requirement and continue other fixes.
>
> Then trace and complete every page/action and all linked services using the route/action method in section 5. Work in small measured batches: reproduce -> root cause -> focused implementation -> regression -> authenticated live check -> evidence ledger. Test text, WebRTC and authorized telephone end-to-end; distinguish each evidence class. Cover roles, two-tenant isolation, model/provider/voice synchronization, agent create/edit/publish, campaigns, tools, files, recordings, CRM, appointments, forms, widgets, templates, runs, billing, reports, admin and install settings. Keep `IMPLEMENTATION_STATUS.md` and `PAGE_ACCEPTANCE.md` accurate and dated. Continue without repeated permission questions for authorized reversible work. Report concrete changes, measured results, remaining failures and next action. Stop claiming the platform is complete until every gate in section 6 has fresh passing evidence.

## 8. Security and operational boundaries

The user supplied VPS credentials in chat previously; obtain them from the authorized environment/session, **never reproduce them in this document, logs, source, tests or a prompt**. Use least exposure and redact private audio/contact data in reports. Work with synthetic contacts and a designated test number for paid telephony. Do not run live campaigns, make purchases or contact arbitrary people as part of verification. Model-card claims, especially language counts and speed, require independent runtime proof. Do not treat a gated model's browser access as a server token. Inspect licenses, trained language quality and model-specific reference-voice consent before adoption.

## 9. Exact working locations, tools and skills

### Local PC versus VPS

| Location | Purpose and observed state |
|---|---|
| `E:\ai\aagent\newai` | Windows source checkout, existing edits, focused tests, documentation and diagnostics. Do not replace it with a clean upstream clone. |
| `E:\ai\aagent\newai\.venv\Scripts\python.exe` | Local Python 3.13.7, used for focused pytest checks. This is development/test tooling, not the production inference runtime. |
| `C:\nvm4w\nodejs\node.exe` | Local Node v20.19.4 at this snapshot; UI tests, TypeScript and client generation use the repository dependencies. |
| `C:\Git\cmd\git.exe` | Source/diff inspection. Capture the worktree, staged changes and nested Pipecat state before edits. |
| `C:\WINDOWS\System32\OpenSSH\ssh.exe` | Connection to authorized VPS `root@72.61.123.8`. Use authorized credentials separately, never embed the password in a prompt or source. |
| `C:\Users\Adarsh\AppData\Local\Programs\Ollama\ollama.exe` | An Ollama executable is installed locally. The process-name check found no matching Ollama/LM Studio/llama-server process at this snapshot. Do not start it or download PC models just because it exists. Production model tests in this continuation ran on the VPS. |
| `/www/wwwroot/default/app.kodewaves.in` | Application checkout/deployment directory on the Linux VPS. Confirm Compose project name, mount paths, overrides, image IDs and environment before changing anything. |
| VPS Docker containers | Production inference and application services. Docker was not found on the local command PATH in this check. Run Docker operations on the intended VPS, not an assumed local engine. |
| Built-in authenticated browser | Used to inspect actual pages and saved settings. Antigravity must use its own available browser integration; a Codex browser/session handle is not portable. |

Local tests may consume PC CPU briefly. Do not install or run local STT/TTS/LLM services unless needed for a specific authorized experiment. Keep the production inference location explicit in every benchmark report.

### Skills that are actually available

Read the skill before applying it. These are instruction files, not proof a feature has been tested, and not substitutes for the task's requirements.

| Skill | Path | Use |
|---|---|---|
| Systematic debugging | `C:\Users\Adarsh\.codex\skills\systematic-debugging\SKILL.md` | Reproduce, inspect evidence, form a specific hypothesis, fix the owning cause. Used in this investigation. |
| Verification before completion | `C:\Users\Adarsh\.codex\skills\verification-before-completion\SKILL.md` | Run fresh relevant checks before claiming success. Used in this investigation. |
| Web application testing | `C:\Users\Adarsh\.codex\skills\webapp-testing\SKILL.md` | Browser journey testing where the destination tool supports the required browser controls. Available; do not assume every historical journey used it. |
| Kodewaves PR review | `E:\ai\aagent\newai\.agents\skills\review-pr\SKILL.md` | Tenant isolation, auth, callbacks, database layering, worker sync and generated clients when reviewing changes. |
| Pipecat upstream merge | `E:\ai\aagent\newai\.agents\skills\merge-pipecat-upstream\SKILL.md` | Only for a necessary upstream sync; protect Kodewaves patches and wrapper contracts. |
| AGENTS documentation review | `E:\ai\aagent\newai\.agents\skills\review-agents-md\SKILL.md` | Audit stale project instructions when needed. |

Other suggested repositories (token savers, subagent collections, account balancers, Superpowers and curated tool lists) were discussed by the user. **This snapshot does not verify that they are installed or active.** Do not claim they saved credits, and do not install a large collection automatically. Use only a relevant, inspected capability. Antigravity may read these local skill files if it has filesystem access; its execution tools will differ from Codex's.

### Practical commands and boundaries

Read `docs/contribution/setup.mdx` and current package files before setup. Use `rg` for targeted search and `git diff` to understand existing work. Never print entire `.env` files.

```powershell
# Windows: inspect, without resetting any work
Set-Location E:\ai\aagent\newai
git status --short
git diff --stat
git diff --check

# Example of the most recent focused local test (no production DB writes)
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pytest api/tests/test_local_speech_aggregator.py -q

# UI commands: run from ui/ after verifying the intended package manager/lockfile
npm run test -- <specific-test-file>
npx tsc --noEmit
npm run build
# Only after an API contract change:
npm run generate-client
```

`api/conftest.py` loads `.env.test`; inspect environment overrides and fixture isolation before any database-writing tests. Repository instructions require `.env.test` for tests and `.env` only for intentional development scripts. A focused unit pass does not authorize running destructive DB fixtures against production.

On the server, inspect `docker compose` configuration, health, image IDs, mounts, active-call counts and application logs with the current project/override arguments. Earlier deployment used both service image builds and app-scoped source mounts, so a host file change alone does not prove a worker uses it. Verify the runtime import/image and restart only affected services when calls are idle. Existing helper scripts include `scripts/benchmark_conversation_model.py`, `scripts/benchmark_local_tts.py` and `scripts/warm_local_ollama.py`; read their inputs and side effects before running them.

## 10. Numbered task backlog with inputs, steps and outputs

All tasks remain open unless the evidence ledger proves their entire acceptance condition. Existing partial fixes should be reused and revalidated, not blindly rewritten.

### T00 — Establish an accurate starting point

**Inputs:** this file, current checkout/diff, `AGENTS.md`, historical status, server access and current deployment.

**Steps:**
1. Record source revision, dirty files, nested repository state, deployed image IDs and mounted source.
2. Record active calls/jobs and CPU/RAM/disk. Do not benchmark while a customer call is running.
3. Map environment variable names to services without recording secret values.
4. Identify which historical fixes are in source, deployed, tested, or merely proposed.
5. Create the source-review and requirement-evidence ledgers described in section 12.

**Output/pass condition:** a reproducible baseline with no ambiguous draft/published/model identities. This is the first task for a replacement agent.

### T01 — Trace one failing voice conversation completely

**Inputs:** workflow 19 or a new disposable equivalent, actual definition/version, native audio, expected transcript and expected response.

**Steps:**
1. Read configuration resolution and pipeline construction from UI save through runtime.
2. Capture timestamps for connection, configured greeting, user speech start/end, STT final, LLM request/first token, first TTS request/audio and first output audio.
3. Capture interruption/cancellation and queued-request events; distinguish repeated caller speech from one fragmented utterance.
4. Confirm exact language, voice, model and tools in the resolved call config.
5. Compare direct-service timings with the same text/audio through the real pipeline.

**Output/pass condition:** a trace identifying the measured delay and incorrect answer cause. Never infer a root cause solely from total latency.

### T02 — Qualify STT and language routing

**Inputs:** installed IndicConformer artifacts, per-language audio corpus, server language configuration.

**Steps:**
1. Inventory actual installed files and supported language codes, not only dropdown entries.
2. Test every required language, English and code-switching with native recordings.
3. Check transcript meaning and original script; detect forced translation or phonetic transliteration errors.
4. Evaluate a language identifier/router only if automatic detection can be supported accurately; benchmark its extra delay and ambiguity handling.
5. Test VAD pauses, quiet microphones, noise, empty input, long input, timeouts and backlog.
6. Keep retired Whisper models out of user selections and remove their artifacts after checking all references. Do not remove working IndicConformer by mistake.

**Output/pass condition:** honest per-language STT availability and measured accuracy/latency; no unsupported auto-detection claim.

### T03 — Qualify the conversational LLM

**Inputs:** exact prompts and history from failing runs, small multilingual task corpus, current Qwen configuration.

**Steps:**
1. Check thinking suppression, output limits, resident model, context length, prompt cache reuse, thread count and cancellation.
2. Test multi-turn requests across delivery support, general support, sales enquiries, account guidance and appointments.
3. Test already supplied names/numbers, corrections, language changes, unclear speech and unavailable tools.
4. Compare candidates using identical prompts on the same idle hardware; measure both quality and prefill/first-token/full-answer timings.
5. Reject reasoning leakage, repeated greeting, invented actions and gibberish even when a model is fast.
6. Promote only a candidate that improves the actual pipeline; remove failed experimental downloads and restore the selected warm model.

**Output/pass condition:** grounded multilingual follow-ups with measured speed. A 2B/4B parameter count is not a quality or speed guarantee.

### T04 — Qualify replacement TTS and voices

**Inputs:** installed Rasa/VITS, candidate model code/cards/artifacts, consented voice references where required, language corpus.

**Steps:**
1. Verify access, license, actual inference interface, CPU support and dependencies.
2. Test Hindi, English and regional languages independently, including names, dates, currency, order numbers and code-switching.
3. Compare intelligibility, accent, pronunciation, natural pauses, voice identity and male/female choices with native listeners.
4. Measure first audio, total synthesis, real-time factor, RAM and CPU; test cold/warm and consecutive requests.
5. Verify sample rate/PCM format, streaming chunk continuity and trailing audio.
6. Retire Indus/Piper/Kokoro only after saved configurations have a validated replacement or an explicit repair path. Do not silently remap a voice to a different gender/language.

**Output/pass condition:** a supported voice matrix and an accepted replacement, not simply a visible new model name.

### T05 — Make turn handling and audio delivery reliable

**Inputs:** T01 trace, selected models, `run_pipeline.py`, STT/TTS adapters, Pipecat turn strategies and playback code.

**Steps:**
1. Ensure greeting audio is prepared appropriately and starts promptly after connection/answer.
2. Cancel obsolete inference/audio on interruption; prevent old-turn audio from cutting into a new reply.
3. Preserve completed words and context while handling interim/final transcripts exactly once.
4. Test first-clause streaming against full-sentence batching; keep it only if audible latency improves without unnatural gaps or cut words.
5. Bound service timeouts and clear pending-turn state after empty/error responses.
6. Test silence, repeated “hello”, barge-in, disconnect during generation and service failure.

**Output/pass condition:** repeatable conversational turns and clean audio; no phantom response, stuck “speaking” state or duplicate answer.

### T06 — Prove text chat

**Inputs:** fresh custom and template agents, permitted configurations and connected test tools.

**Steps:** create -> save -> reload -> test three or more turns -> change language -> supply/correct details -> invoke a real test tool -> inspect persisted run. Test missing provider and unavailable tool paths.

**Output/pass condition:** correct context, honest tool results, visible errors, exact configuration and scoped stored transcript.

### T07 — Prove browser audio

**Inputs:** T02–T05 models, authenticated browser, microphone/consented recorded audio and WebRTC connectivity.

**Steps:** permission -> connect -> greeting -> three follow-ups -> interruption -> language change -> disconnect -> inspect audio/transcript/metrics. Repeat with a new user and a freshly created agent. Check TURN/network fallback separately.

**Output/pass condition:** complete spoken journey with native-listener acceptance and measured latency. Synthetic audio tests are useful diagnostics but not substitutes for microphone and listening checks.

### T08 — Prove telephone audio

**Inputs:** configured provider, owned number, explicitly designated test destination and published agent.

**Steps:** validate signed callbacks -> inbound call -> answer/greeting -> three follow-ups -> interruption -> transfer if configured -> hangup -> recording/run/billing reconciliation. Repeat authorized outbound. Check codec/resampling, duplicate and out-of-order callbacks, disconnect and capacity errors.

**Output/pass condition:** verified inbound/outbound conversation on the phone, no early hangup, silent follow-up or delayed announcement. Do not claim success from a provider “connected” status or bytes sent.

### T09 — Synchronize model, voice and capability configuration

**Inputs:** catalog, local inventory, organization policy, admin settings, workflow versions and runtime resolution.

**Steps:** map admin enable/disable -> user visibility -> editor validation -> saved config -> draft test -> publish -> campaign/widget/phone runtime. Verify voice lists by model/language/gender, stale selections, installed/deleted models, source attribution and multi-worker propagation.

**Output/pass condition:** the chosen usable configuration runs everywhere; missing capability produces a clear repairable error and no silent vendor fallback.

### T10 — Complete agent creation, builder and templates

**Inputs:** new user, blank agent, every offered template, tool and model configuration.

**Steps:** exercise all builder panels and settings; create/edit/delete nodes and edges; validate invalid graphs; save/reload; test; publish; compare draft/published; inspect failed-create errors. Check optional company name and greetings. Test several business services, not only appointments.

**Output/pass condition:** newly created agents work without hidden manual database repairs. Private/admin instructions never leak into customer-facing answers.

### T11 — Complete identity, roles and tenant isolation

**Inputs:** two organizations and regular/admin accounts.

**Steps:** signup/login/logout/session expiry -> organization switching -> role changes -> direct API denial tests. Check every page/menu and resource ID, recordings/files/exports, provider credentials, public widgets/forms and callbacks.

**Output/pass condition:** ordinary users cannot see or exercise admin capabilities or another tenant's resources, even by direct requests.

### T12 — Complete telephony setup and campaigns

**Inputs:** tested phone configuration, published agent, synthetic contacts and campaign worker.

**Steps:** create/edit provider -> assign number -> readiness errors; create campaign -> validate contacts -> schedule IST -> start -> retry limits -> pause/stop/resume -> terminal results. Test capacity admission, duplicate jobs and worker restart recovery.

**Output/pass condition:** consistent campaign/number/run state and no duplicate unintended calls. Live customer campaigns remain outside diagnostic tests.

### T13 — Complete tools, files and knowledge retrieval

**Inputs:** tool definitions, test endpoints, supported document types and scoped storage.

**Steps:** CRUD/validate tools; test credentials, timeout and failure messages; upload/process/index/retrieve files; verify failed jobs and retry/delete; invoke retrieval from an agent; verify result grounding and access.

**Output/pass condition:** real connected actions and relevant scoped knowledge with no false success or secret leakage.

### T14 — Complete CRM and appointments

**Inputs:** synthetic lead/contact and appointment fixtures, connected agent tools.

**Steps:** CRUD, search/filter/pagination, duplicate handling, timezone/date boundaries, tool writeback, edit/cancel, concurrent updates and reload. Test unavailable booking tools without fictional confirmations.

**Output/pass condition:** correct persistent records and accurate agent confirmations only after successful storage/tool results.

### T15 — Complete forms, widgets and public surfaces

**Inputs:** a new form/widget and published agent, authorized embed page.

**Steps:** create/edit/publish/embed -> submit or chat/audio -> inspect run/lead -> change configuration -> verify propagation. Test stale responses, identity changes, invalid input, revoked publication and tenant boundaries.

**Output/pass condition:** embeds and forms perform their intended action with secure scoping, useful errors and consistent saved results.

### T16 — Complete recordings, runs, overview and reports

**Inputs:** known successful/failed text/web/phone runs and their raw event records.

**Steps:** verify transcript/audio alignment, playback/download access, filters/pagination, deletion, run status, timing labels, model attribution, overview totals, report totals and exports. Trace each displayed number to its source.

**Output/pass condition:** pages match actual runtime facts and do not hide failed runs or fabricate analytics.

### T17 — Complete wallet, pricing and billing integrity

**Inputs:** published admin rates, sandbox payments and known local/BYOK/cloud/carrier runs.

**Steps:** verify source-based prices, wallet credit/debit, insufficient funds, replayed receipts, duplicate completion and concurrent charges. Reconcile run detail, wallet, admin totals and reports. Use payment sandbox fixtures.

**Output/pass condition:** no forged credit, double charge or client-controlled price; customer-visible charges match trusted runtime usage.

### T18 — Complete administration and monitoring

**Inputs:** platform admin and regular user sessions, all admin child routes.

**Steps:** test user/plan/model/settings/moderation/audit/monitoring actions; verify backend authorization and cross-worker updates; check real emergency call termination and resource metrics. Test partial service failure and useful recovery messages.

**Output/pass condition:** each control performs the stated action, and regular users cannot exercise it.

### T19 — Make installation, branding and regions portable

**Inputs:** fresh isolated deployment, repository Compose/setup scripts, alternate hostname/brand.

**Steps:** configure secrets/domain/brand/region at installation; migrate/seed/start/restart; verify URLs, callbacks, certificates, storage and workers. Search for hardcoded Kodewaves production domain/IP and workflow-specific behavior. Preserve upstream notices/licenses where required.

**Output/pass condition:** the same product works under a customer brand and VPS without code edits tied to this server. India/IST is the intended default without unnecessary caller timezone questions.

### T20 — Resource limits, cleanup and recovery

**Inputs:** live resource measurements, model/container dependency inventory and backups.

**Steps:** bound inference concurrency/threads; test overload admission and queue behavior; inspect swap/OOM/restarts; prune only proven unused artifacts; record reclaimed space; test restart and backup/restore in isolation.

**Output/pass condition:** no shared-host overload, no deletion of active models/volumes, documented supported concurrent-call capacity and recovery.

### T21 — Final acceptance and delivery

**Inputs:** all previous task evidence, fresh-user fixtures and the intended production build.

**Steps:** rerun the complete user/admin journeys; audit every original requirement against current evidence; verify rollback/runbook and unresolved issue list; perform final security/tenant/billing checks and language/audio qualification.

**Output/pass condition:** every explicit requirement is passed with current evidence. Otherwise deliver an exact remaining-work list and continue; never relabel an incomplete target as complete.

## 11. How each task is executed day to day

Use this sequence for every meaningful batch:

1. **Read:** identify the owning files and their instructions; read the relevant implementation and call sites line by line. Record what is read, not just searched.
2. **Explain the contract:** write the input, output, state transition, failure behavior and tenant boundary in the ledger.
3. **Reproduce:** use a minimal representative scenario with the actual config and record before behavior.
4. **Hypothesis:** state one cause supported by the trace. Avoid changing models, prompts, timing and voice all at once.
5. **Implement:** change the shared owning layer, preserving unrelated edits and custom branding.
6. **Verify locally:** meaningful focused regression, then necessary related checks. Do not repeatedly run the entire suite without a new reason.
7. **Deploy if relevant:** verify no active call, take a rollback snapshot, update affected runtime only, confirm actual version and health.
8. **Verify live:** same input/config as before; check persisted outputs and real audio/actions. Abort a diagnostic if a user call begins.
9. **Compare:** quality, first audio, full response, error rate and CPU/RAM. Reject a change that merely hides failures or worsens conversation.
10. **Record:** changed files, exact result, run ID, current limitations and next task. Keep evidence concise and avoid dumping raw logs into chat.

Do not spend a day repeatedly probing the same failed model with no new hypothesis. After a controlled comparison disproves a candidate, record the result and move to a different actionable cause or independent platform task. Do not wait for a model-access prerequisite while leaving unrelated authorized work untouched.

## 12. Required task and evidence records

Use existing status files where possible; do not create several competing plans. Add these tables to local reports if absent:

```text
TASK:
  ID / requirement / priority / status / dependencies
  inputs and selected runtime config
  owning files + reviewed revision/hash
  reproduction + expected output
  root cause + implementation diff
  regression command + result
  live run ID + environment + timing/quality evidence
  unresolved limitation + next action

FILE REVIEW:
  path / purpose / callers / dependencies
  not-read | partially-read | fully-read
  correctness/security findings / relevant test and runtime evidence

PAGE ACTION:
  route / section / control / API method+path
  role + organization scope / validation / persisted side effect
  happy path / error path / reload / second-tenant check / evidence

LANGUAGE:
  language / script / STT installed+accuracy / LLM quality
  TTS voice+gender / accent+intelligibility / code-switching
  text / web / phone / warm+cold timing / native-listener result
```

The documentation does **not** certify that every source line has already been reviewed. It specifies how to perform and prove that review. Never replace “unreviewed” with “passed” because a text search found no match.

## 13. Latest continuation state and exact resumption point

Updated after this handoff's first draft:

- A diagnostic run (#264) overlapped the user's #263, so some earlier timing evidence is contaminated by competing CPU work. It does not explain away the later isolated failures.
- `run-webrtc-two-turn.py` now checks fleet-wide active calls before starting/synthesizing and cancels its diagnostic path if another call appears. It also resolves the actual draft instead of silently passing the published definition with `use_draft=True`. It is an **untracked diagnostic**, not a production feature, and must stay unpushed.
- The server's guarded Kannada probe completed as **run #266** with no overlap reported. First audible follow-ups were **15.506 seconds and 11.427 seconds**. Greeting audio started 2.912 seconds after the probe's timer origin. These are still failures of the requested latency target; timer origin and end-of-user-speech metrics must not be confused.
- An **optional, disabled-by-default** first-clause release was added locally in `api/services/pipecat/local_speech_aggregator.py` as `first_clause_characters`. It splits only at comma/semicolon-style punctuation followed by whitespace after a minimum length, preserves numeric commas, and resets on interruption. It has **not been enabled in production or accepted acoustically**.
- Twelve focused aggregation tests passed on 20 October using the local Python environment. Two old integration expectations were aligned with the already existing 24-character first-sentence behavior. This does not prove an actual latency improvement.
- The isolated, process-only clause candidate completed as **run #267**: first audible follow-ups were **6.272 seconds and 6.293 seconds**. No overlap marker was reported. LLM first-token times also changed (0.299/1.844s versus baseline 1.686/2.028s), and answers varied, so the total improvement cannot be assigned solely to the clause change. Both #266 and #267 falsely offered an order check despite having zero tools. **Conversation grounding remains failed; the candidate was not promoted to production.**
- Actual captured model requests contained the corrected 3,370-character system prompt, no tools, preserved Kannada user history, and `think: false`. Missing history or an unpropagated draft correction does not explain these specific invalid answers. A separate direct two-turn request with an additional explicit no-tools capability statement timed out after 40 seconds on its first request; it was not deployed as a prompt fix.
- Immediate next task: qualify a model/architecture that follows tool limitations and produces correct native-language answers; keep the optional clause change disabled until causal replay and acoustic checks justify it. Continue T02/T03 and the independent platform backlog. Do not launch another production user call as a benchmark.
- Transient server files from the current session are inside `kodewaves_api` under `/tmp/`: `kodewaves-kn-draft-probe.py`, `kodewaves-kn-isolated.log`, and earlier `kodewaves-kn-draft-fixed.log`. They may disappear on recreation. Persist only redacted acceptance evidence to the local status file; do not rely on these temporary files as the sole handoff.
- Additional temporary candidate artifacts: `kodewaves_clause_candidate.py`, `kodewaves-kn-clause-probe.py`, `kodewaves-kn-clause.log`, and `kodewaves-capability-probe.py`. Candidate imports affected only the diagnostic Python process; no application worker or live selection was replaced.

An alternative research direction is an entirely self-hosted translation bridge around a stronger English conversation path while retaining the caller's original transcript. [AI4Bharat's official IndicTrans2 repository](https://github.com/AI4Bharat/IndicTrans2) covers the 22 scheduled languages; its [distilled English-to-Indic card](https://huggingface.co/ai4bharat/indictrans2-en-indic-dist-200M) requires access-condition acceptance and recommends the newer Indic-Translate family. This is **unqualified research**, with no downloaded/installed bridge or latency claim. Review both directions, number/name preservation, gender grammar, code-switching, extra CPU cost, model licenses and human translation quality before adoption. Do not turn this option into a cloud dependency or silently alter displayed user speech.

## 14. Additional prompt for the receiving agent

> Treat sections 9–13 as the practical execution runbook. Begin with T00 and confirm the latest state before running anything. Maintain the task, file-review, page-action and language ledgers. Execute T01–T08 first for the speech priority while progressing independent platform tasks T09–T20 when a real dependency blocks speech. Use the skills listed in section 9 where applicable and only tools available in your environment. Local Python/Node are for development; production inference runs on the VPS. Do not start the installed local Ollama or download large PC models unnecessarily. Do not treat the optional clause experiment, a model dropdown entry, a healthy container or a passing unit suite as a completed product. Deliver actual corrected behavior and measured acceptance for every task, with no unsupported claim of all-language or 800 ms readiness.
