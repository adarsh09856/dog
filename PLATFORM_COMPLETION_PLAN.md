# Complete platform delivery plan

Date: 2026-10-07. Scope: the entire Kodewaves product in this repository, including every user and administrator page and the services behind them. This is the detailed execution plan; `IMPLEMENTATION_STATUS.md` records completed work and `PAGE_ACCEPTANCE.md` records page acceptance. The earlier `IMPLEMENTATION_PLAN.md` remains the summary.

## 1. The required outcome

A new user can sign up, enter the correct workspace, configure permitted credentials and telephony, choose STT/LLM/TTS independently, create and publish an agent, test it through the browser and telephone, run campaigns, receive incoming calls, and use bookings, CRM, files, tools, forms, widgets, logs, recordings and reports. Every action persists correctly, has accurate permissions and displays a useful error when it cannot succeed. Administrators can configure and operate the whole platform through working controls.

Cloud models appear only when the administrator enables and provides the corresponding platform capabilities. User-owned credentials are a separate, explicitly permitted BYOK path. Local models appear only when the engine is available, the models/voices are ready and the workspace has access. Saved configurations retain the chosen model, voice, language, source and settings through editing, testing, publishing and execution. Any substitution requires an explicitly configured policy and visible attribution.

Billing reflects the services actually used under the administrator's published rates, including mixed-source calls. Self-hosted and BYOK usage are not assumed free: platform and carrier charges must be explicitly defined and explained. No secret is returned to another user or placed in logs, reports or Git.

## 2. Current starting point

The platform is not complete. The recorded baseline includes 190 passing frontend tests, a passing TypeScript check and 26 passing targeted backend tests. These are evidence for selected components, not proof of a working deployment or all pages. Several authentication, CRM, model-resolution and local-engine controls have been repaired. Live browser/telephone journeys, full database integration, complete source review and performance qualification remain unfinished.

Reproduce relevant baseline checks when their inputs or environment change. Preserve existing changes and staged deletions. Recheck old findings against current source before modifying it; some audit scripts intentionally reproduce defects that have already been fixed.

## 3. Coverage and evidence system

Create and maintain these local records under the existing audit/report directory:

| Record | Required contents |
|---|---|
| File coverage ledger | Relative path, file class, review status, purpose, dependencies, findings, reviewer evidence and revision/hash |
| Route/action matrix | UI entry point, control/action, API method/path, auth/role, organization scope, service, DB objects, job and external dependency |
| Finding register | ID, severity, reproduction, expected/actual behavior, affected journey/files, fix, regression evidence, remaining limits |
| Provider matrix | Provider, layer, credential source, models/voices, languages, transport, configuration/contract/live status and failures |
| Journey results | Preconditions, steps, expected results, actual results, test environment, evidence locations and timestamp |
| Performance results | Hardware, model versions, concurrency, audio corpus, sample counts, latency distribution, errors and accuracy |

Coverage states: not read, partially read, fully read, implemented, test verified, live verified, blocked. Review and runtime verification are separate fields; a file can be fully read while its feature remains blocked.

Inventory all tracked and relevant untracked files, all route types, background jobs, public endpoints, WebSockets, command scripts and the Pipecat submodule. Read human-authored source/configuration/migrations/tests/docs completely, in bounded sections for large files. Review submodule source and modifications with separate counts. Classify generated SDKs, lockfiles, binary assets, model weights and installed dependency/build directories explicitly; validate them through generation, parsers, integrity/metadata or build checks instead of calling a scan a complete manual read. Do not silently omit them from inventory. Do not print secret-bearing environment file contents; inspect required variable presence and validity with redaction.

For every page, include child components, shared hooks, modal actions, validation, API contracts, backend services, persistence and background effects. Extend `PAGE_ACCEPTANCE.md` whenever another route is discovered; it is a checklist, not a scope limit.

## 4. Phase 0 — Reproducible local environment

1. Inspect applicable `AGENTS.md`, current diff, existing audit records and supported setup scripts.
2. Record versions of Python, Node, database, Redis, storage, Pipecat and dependencies; install from repository specifications and note deviations.
3. Bring up the frontend, API, PostgreSQL, Redis, MinIO, required workers and local inference services. Verify service health and dependencies rather than only listening ports.
4. Use isolated development fixtures and a separate test database. Backend tests load `api/.env.test`, never `api/.env`. Abort database test setup if isolation cannot be demonstrated.
5. Create disposable admin/user fixtures in two workspaces with different roles and policies. Use synthetic contacts, audio, bookings and transactions.
6. Record migrations, seed behavior, worker startup, storage permissions, callback URLs and browser transport readiness. Verify cleanup and restart persistence.

Exit evidence: repeatable startup/runbook, healthy dependency checks and successful isolated test-DB migration. Missing infrastructure is recorded; independent code work continues.

## 5. Phase 1 — Identity, workspaces and shared frontend behavior

Cover signup, login, logout, auth callbacks, session expiry, refresh and account/workspace loading for each supported authentication mode. Validate account provisioning and organization membership. Check regular users cannot enter admin routes or call admin APIs; suspended workspaces cannot run calls. Exercise two-workspace switching and prove data/caches do not leak between them.

Repair shared API authentication, error handling and contracts before patching every page independently. Verify loading, empty states, retry, validation, double-submit prevention, pagination, filters and unsaved edits. Successful writes must survive reload. Failed writes must not show success. Regenerate SDKs from the API when contracts change; never hand-edit generated files.

Exit evidence: authenticated browser sessions for admin and user roles, negative role/tenant API tests, and working session lifecycle.

## 6. Phase 2 — Administrator catalog, BYOK and model selection

Trace admin credential entry → encryption → validation → enabled catalog → workspace policy → user selection → stored agent → runtime resolution → usage attribution.

- Add, validate, rotate, disable and remove each supported credential type. Distinguish configured, reachable, validated and unavailable states. Never expose saved secrets in read responses.
- Catalog identity must include provider, layer and model identity. Enforce enabled status, workspace policy and credential availability in both dropdowns and execution. Revoke stale selections reliably across workers.
- Independently choose local/cloud/BYOK for STT, LLM and TTS. Persist language, voice, endpoints, model parameters and credential source. Preserve custom endpoint semantics for providers that support them.
- Make BYOK an explicit source. Reject disallowed keys clearly; do not silently substitute a billable platform key. Keep administrator-provided keys out of user-visible configuration.
- Define precedence among workspace defaults, saved agent overrides and permitted test overrides. Resolve once into an immutable run snapshot with trusted provenance and pricing version.
- Handle realtime/S2S as its own mode; do not require unrelated STT/LLM/TTS credentials when the selected realtime provider supplies them.
- Make absent or unavailable models fail preflight with an actionable message. Do not select a hard-coded local model that has not been installed.

Exit evidence: round-trip save/reload and runtime tests for every supported source combination, revoked keys/models, BYOK denial, workspace access denial, voice/language preservation and multi-worker refresh.

## 7. Phase 3 — Self-hosted inference first, then cloud adapters

The user's priority is local/self-hosted agent testing first. Verify Ollama, Whisper and Piper contracts against actual installed models before testing cloud providers.

- Implement truthful installed/loaded/healthy states, exact model/voice selection, preload, download progress, unload and failure reporting.
- Check model paths, endpoint normalization, sample formats, WAV headers, PCM rates/channels, transport conversion and adapter compatibility with the pinned Pipecat version.
- Fix STT utterance segmentation and silence handling; transport chunks must not be incorrectly treated as full utterances. Surface provider errors to the pipeline and UI.
- Verify TTS completion frames, source sample rates, voice selection, streaming where supported and cancellation during barge-in. Never invent timing measurements.
- Bound inference work and queue depth; handle cancellation, timeouts, overload and resource release. Keep health/admin requests responsive during inference.
- Run real synthetic audio through STT → LLM → TTS and then the actual voice-agent pipeline. Repeat with cold and warm models.
- Build adapter contract tests for every exposed cloud provider. For each configured provider, run a live layer test and a complete supported call. Providers without credentials remain explicitly unverified.

Exit evidence: working local audio journey and measured local agent call; truthful compatibility matrix for cloud adapters. Removing a failing feature from the menu alone does not complete its implementation.

## 8. Phase 4 — Agent editor, tools and browser calls

Cover agent creation, templates, graph editing, validation, save, reload, duplication, publishing, versioning, settings and deletion rules. Validate every node type and transition, variables, prompts, knowledge retrieval, structured extraction, tool calls, transfer and end-call behavior. Validate ownership of all linked tools/files/configurations.

Use one published snapshot for all run settings. Test edits after a call is created to ensure in-flight calls do not change unexpectedly. Readiness checks must report missing models, credentials, telephone configuration and inaccessible dependencies.

Test browser microphone permission, connection establishment, device selection where offered, audio in both directions, transcripts, response playback, interruption, silence, disconnect, timeout and reconnect behavior. Test embedded widgets with domain restrictions, scoped tokens and expiry. Never expose privileged credentials to the widget.

Exit evidence: create → configure → publish → browser call → tool action → hangup → persisted run/transcript/recording, including failure journeys.

## 9. Phase 5 — Telephony and incoming/outgoing calls

For every carrier exposed by the product, trace configuration, validation, number registration/import, number assignment, inbound routing, outbound initiation, media connection, status callbacks, transfer and cleanup.

- Validate carrier credentials without creating unnecessary external resources. Bind numbers and configurations to the correct workspace.
- Authorize foreign keys on save: number, agent, workflow, campaign and carrier configuration must belong to the workspace.
- Verify webhook signatures using each carrier's documented canonical request rules, trusted external URL configuration and replay controls where supported. Validate call/run/workspace relationships before issuing media capabilities or taking carrier actions.
- Verify WebSocket authorization, capability expiry and single-use rules where applicable. Do not let unsigned answer routes mint valid media tokens.
- Make admission atomic across workers. Reconcile duplicate/out-of-order callbacks and preserve terminal states. Ensure failed setup releases capacity.
- Make transfer state durable; fast answers must not be lost before subscribers attach. Verify successful, rejected, unanswered and timed-out transfers and both call legs' cleanup.
- Admin hangup must terminate the carrier/media call and release resources, not only change a database label.

Live testing requires a designated test destination/owned number and working callback reachability. Credentials alone are not permission to call arbitrary contacts. Do local/simulated verification while these inputs are unavailable. Do not purchase numbers or place calls to campaign contacts for testing.

Exit evidence: authorized outgoing and incoming calls, two-way audio, transfer, remote/local hangup, correct run logs and billing for each configured supported carrier. Unconfigured carriers have separate contract-only status.

## 10. Phase 6 — Billing, plans and usage integrity

Document the rate rules before coding them: platform-model fees per layer, local hosting fees if any, BYOK platform fees if any, carrier charges, realtime pricing, rounding, minimums, currencies, credits and bonuses. Do not invent business prices; use configured rates and mark missing decisions explicitly.

Persist actual server-resolved source/model/rate version per run. Confirm mixed configurations use the proper charge components. Admission and completion must handle balance, quotas and concurrency consistently. A client-supplied flag cannot waive or alter fees.

Use atomic ledger transactions and stable idempotency keys. Test duplicate completion, concurrent calls, partial failures, refunds/adjustments, zero balance, rounding and reconciliation. Authenticate payment callbacks and verify amount, currency, account and order before crediting. Never credit based on an unverified browser receipt.

Check user wallet, plan, package, usage, history and invoice displays against the ledger; check admin adjustments and plan edits are permissioned and audited. Run payment-provider journeys in sandbox mode only.

Exit evidence: isolated database integration tests for concurrency/replays, sandbox payment reconciliation and exact agreement between known call charges, ledger, UI and exports.

## 11. Phase 7 — Campaigns and background execution

Cover CSV/source import, validation, duplicates, contact mapping, agent/carrier selection, timezone scheduling, preflight, start, pause, resume, stop, retries and results. Respect configured consent/suppression/calling-window rules where the product supports them. Use synthetic recipients for test execution.

Verify durable per-recipient state, atomic claiming, capacity/wallet admission, retry limits/backoff and restart recovery. Pause/stop must stop future dispatch; clearly define handling of calls already active. Duplicate jobs and callbacks must not create duplicate calls or charges. Pin published agent configuration and record per-call outcomes. Test a worker crash after carrier acceptance and reconcile rather than blindly redialing.

Exit evidence: a small isolated campaign completes through success, busy/no-answer, failure, retry, pause/resume and worker restart, with consistent CRM, logs and billing.

## 12. Phase 8 — Every user-facing feature

| Feature/pages | Required journey and edge cases |
|---|---|
| Overview | Real workspace metrics, date boundaries, empty state and linked navigation |
| CRM | Contact CRUD/import/search/pagination, tags/stages/notes, duplicates, timeline, agent writeback and cross-workspace rejection |
| Appointments | Create/reschedule/cancel, timezone/DST, availability, concurrent double-booking prevention, contact link and agent confirmation; verify external calendar sync only when configured |
| Files/knowledge | Upload limits/types, storage, ingestion/index status, retrieval relevance, failed jobs, download/delete, index cleanup and permissions |
| Tools | Schema validation, credentials, test invocation, timeout/retry, result handling, ownership and workflow linkage |
| Forms | Stable identifiers/slugs, field editing and validation, publish/submit, public access rules, submissions, duplicate handling and downstream linkage |
| Widgets | Published-agent assignment, embed, domain/token checks, browser call, limits and revocation |
| Templates | Real lists, search, create/edit/copy/use, workspace/shared ownership and persistence |
| Automation | Actual trigger/action execution, enable/disable, schedules, retries, idempotency, run history and errors |
| Recordings | Upload/list/play/download/delete, authorization, range/content types, expiry and retention |
| Runs/logs/reports | Correct call lifecycle, transcript ordering, tool events, errors, recordings, pagination/filter/export, timezone and workspace isolation |
| Usage/billing | Ledger reconciliation, filters, pagination, plan/package actions and payment failures |
| Settings | Profile/workspace preferences, integrations, key rotation, persistence and access changes |
| Public/auth pages | Navigation, real pricing/configuration consistency, signup/login/callback/logout and useful failures |

Apply this table to all routes in `PAGE_ACCEPTANCE.md`, including dynamic routes and shared components. Inspect controls not named here and add their journeys. A visible button with no implemented action is an unresolved defect; an external dependency must produce a clear setup requirement, never fake success.

## 13. Phase 9 — Every administrator feature

Verify dashboard totals, users/workspaces, role/status changes, master credentials/models/voices, local engine management, plans/packages/prices, billing adjustments, branding/settings, SMTP, payment settings, moderation, audit logs, monitoring and superadmin run inspection.

Check validation, persistence, revocation and multi-worker propagation for each write. Ensure masked-secret edits preserve existing values correctly and explicit replacement/removal works. Verify monitoring reports actual service/call/resource states; unreachable services must not display healthy fabricated statistics. Cross-workspace operations must require administrator authority and be audited. Test recovery after disabling then re-enabling a service or workspace.

Exit evidence: authenticated administrator journeys for every route/action and negative authorization tests from normal users.

## 14. Phase 10 — Accuracy, latency and operational reliability

Create a versioned synthetic/authorized evaluation corpus for the supported languages, accents, short/long speech, silence, background noise, interruptions, names, dates and telephone-quality audio. Keep training/model selection separate from held-out evaluation.

Measure speech-end → final transcript, LLM time to first token, TTS time to first audio, user speech-end → first audible reply, total response time, interruption-stop delay, call setup and failure rate. Record p50/p95, sample count and cold/warm conditions at concurrency 1, 2 and the configured supported limit. Record CPU/GPU/RAM and model settings.

Measure word/character error rate as appropriate, task completion, booking-field correctness, contact extraction and tool success. Repeat identical scenarios across local/cloud/mixed configurations. Optimize the measured bottleneck, then rerun correctness and audio tests. Proposed engineering targets must be labeled provisional until hardware, language and workload are known; do not promise a universal millisecond latency or accuracy percentage.

Exercise worker/service restart, Redis/database interruption, storage failure, provider rate limits, key revocation, expired sessions, network loss and overload. Verify backpressure, bounded retries, resource cleanup, observable errors, backup/restore and recovery documentation.

Exit evidence: reproducible measurements against recorded targets and no unresolved blocking reliability defects at the supported workload. Production deployment remains a separate explicit action.

## 15. Test matrix and execution order

First exercise local STT + local LLM + local TTS. Then platform cloud only, BYOK only and all eight local/platform source combinations across the three layers. Add BYOK substitutions at each layer and representative cross-vendor combinations; maintain a complete supported combination list and use compatibility groups only with an explicit rationale. Test realtime separately.

For each configuration, verify save/reload, preflight, actual resolved identity, web call, authorized phone call, interruption, failure reporting, logs and charging. Run representative full journeys live; use contract/integration coverage to cover wider permutations. Label live versus mocked evidence explicitly.

Execution order: environment and shared identity → catalog/source policy → local runtime → agent/browser call → telephony → billing and campaign completion → remaining user/admin journeys → multi-worker/performance/recovery → final regression. Fix critical authorization and financial integrity defects before external call/payment tests. Page audits and documentation can proceed whenever dependencies are ready.

## 16. Definition of complete

All of the following are required:

1. Inventory is reconciled; every human-authored file has full review evidence, and generated/binary/dependency files have explicit validation/classification. No partial read is called complete.
2. Every discovered page/action/API/job has an owner journey and result. Authenticated admin/user acceptance passes with persistence and failure cases.
3. Supported configured model and carrier integrations have the required live evidence. Unavailable credentials or hardware remain visible blockers; they cannot count as a pass.
4. The new-user journey succeeds from signup through model/telephone setup, agent publishing, web/phone calls, campaign/inbound handling, booking/CRM updates and usage/recordings/report reconciliation.
5. Tenant/role isolation, callback authentication, source attribution, concurrent billing and worker recovery checks pass.
6. No unresolved critical/high defect remains in supported journeys. Lower-severity limitations are explicitly documented with impact.
7. Accuracy/latency targets and supported concurrency are recorded and met on documented hardware; unsupported workloads are identified.
8. Builds, relevant test suites, migrations, generated-client checks and clean-start validation pass. Changes have been reviewed against existing user edits.
9. Deliver final evidence report, file/page/provider matrices, setup/runbook, migration/rollback notes and a clear remaining-blocker list if completion is not achieved.

Keep all work local. Do not commit, push, open a PR, publish, deploy or upload test artifacts as part of this plan. Ask only for information or external actions that are genuinely missing; continue independent authorized implementation while blocked. No estimate is a substitute for acceptance evidence.


## Accepted product benefits — 15 October 2026

These extend the existing complete-platform scope; none replaces page/action acceptance.

| Benefit | Required implementation and acceptance evidence |
|---|---|
| Reliable business actions | Persisted tool outcomes, tenant isolation, idempotent retries and truthful caller confirmations across booking, CRM, campaigns, forms and integrations. |
| Indian conversation accuracy | Representative Hindi/Hinglish/English and supported regional-language corpus; names, phone digits, addresses, amounts, dates, interruptions; measured errors by language. |
| Private deployment choices | Explicit local/cloud/mixed source per layer, credential ownership, data destinations and retention visible; no silent fallback outside the selected policy. |
| Guided setup | Auth/workspace, carrier readiness, installed/authorized model and voice compatibility checked; actual web and telephone journey required before publish readiness. |
| Useful failure recovery | Visible provider/quota/transport/tool errors, preserved collected data, safe retry, authorized transfer/callback; never simulate successful actions. |
| Transparent cost and performance | Actual carrier/platform/provider usage attribution, saved rate version, first-audio and turn-latency distributions, successful-outcome cost. |
| Complete business templates | Published receptionist/qualification/support templates connected to real tools, CRM, appointments, recordings, runs and reports. |

Execution priority: finish current speech/provider defects, then all Build, Growth & Leads, Manage and Administration action journeys listed in PAGE_ACCEPTANCE.md. CRM is included. New visual identity is deferred until functional acceptance. Features remain proposed until evidence marks them implemented and verified. No new architecture/model training has been authorized as a separate research project by this plan.
