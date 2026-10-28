# Reusable implementation prompt

Continue working in `E:\ai\aagent\newai` until the entire Kodewaves platform satisfies the acceptance criteria in `PLATFORM_COMPLETION_PLAN.md`. Read that plan, `IMPLEMENTATION_STATUS.md`, `PAGE_ACCEPTANCE.md`, the existing audit reports and applicable `AGENTS.md` instructions first. This is an implementation task: audit, reproduce, repair, test and document the actual product. Do not stop at a plan or claim completion from scans or isolated passing tests.

## My intended product

A user must be able to sign up, select their workspace, configure telephone credentials/numbers, choose permitted STT, LLM and TTS models, create and publish an agent, test a browser call and a telephone call, run campaigns and handle incoming calls. Bookings, CRM actions, tools, knowledge files, forms, widgets, automations, transcripts, recordings, logs, usage and billing must work together. Every existing user page and every admin/superadmin page is in scope, including features not listed in my examples.

An administrator controls available platform cloud credentials/models and self-hosted capabilities. Users see only permitted ready options. BYOK is available only when allowed. Users can choose cloud, local or allowed BYOK independently for STT/LLM/TTS, including mixed providers. Preserve the exact selected models, language, voice, settings and source through save, reload, test, publish and execution. Enforce restrictions again at runtime; do not silently change providers or replace a user key with a charged platform key. Realtime/S2S must have its own correct configuration and runtime path.

Billing must use trusted runtime information and configured rates for the actual services used. Do not invent prices or assume BYOK/local means free. Prevent duplicate charges, forged credits and concurrent balance errors. User/admin totals, logs and exports must reconcile.

## How to execute

1. Inspect the current workspace and preserve all pre-existing edits and staged changes. Determine which fixes already exist. Do not restart the audit from zero or overwrite user work.
2. Build/reconcile a complete file inventory. Read every human-authored source/configuration/test/migration/documentation file fully, including shared components, workers, scripts, SDK source and Pipecat source. Track not-read, partial-read and full-read status honestly. Classify generated code, lockfiles, binaries and installed dependencies separately and validate them appropriately. Never expose environment secrets while reviewing configuration.
3. Map every UI action through its API, authorization, workspace boundary, service, database, worker and external provider. Include hidden/shared controls and public endpoints, not only page entry files. Maintain file, page/action, route, provider and finding matrices.
4. Establish a reproducible running local stack and isolated test fixtures for an admin and users in two workspaces. Backend tests must use `api/.env.test`, never the development/production database. Prove isolation before migrations or database-writing tests.
5. Prioritize the complete self-hosted agent journey first: actual installed local STT → LLM → TTS, then agent browser calls. Verify exact model/voice selection, speech segmentation, audio rates, interruptions, timeouts and resource cleanup. Then exercise configured cloud/BYOK/mixed and realtime paths.
6. Fix identity, shared API contracts and model policy at their common source. Resolve immutable call configuration with trusted credential-source and pricing attribution. Regenerate generated clients when needed; do not hand-edit them. Use DB clients for queries/transactions and worker synchronization for shared cached settings.
7. Complete telephony configuration, number assignment, inbound/outbound calls, signed callbacks, authorized media, transfer, hangup, atomic capacity admission and cleanup. Treat duplicated, early and out-of-order callbacks as normal cases to test.
8. Complete billing/payment integrity, campaign lifecycle and worker recovery. Use payment sandbox fixtures. Campaign tests use synthetic contacts and designated test destinations only.
9. Complete every user and administrator journey in `PAGE_ACCEPTANCE.md`; discover and add any missing routes/features. Verify loading, empty states, validation, errors, persistence, permissions, pagination, filters and every offered action. Fix misleading success messages, fabricated metrics and disconnected controls.
10. Write meaningful regressions for actual defects, run relevant unit/contract/database tests, build/typecheck the frontend and test authenticated browser journeys. Use real configured services for live acceptance. Label mocks, code review, simulated requests and live evidence separately.
11. Measure accuracy and latency with a documented corpus, hardware, model versions, cold/warm conditions and concurrency. Report p50/p95 and failure rates. Optimize observed bottlenecks without silently changing selected models or hiding accuracy loss. Do not claim low latency from one direct service request.
12. Verify deployment configuration, migrations, generated clients, multi-worker synchronization, restart recovery, storage cleanup and backup/restore instructions. Produce reproducible setup and troubleshooting notes.

## Operational boundaries

Keep all changes, tests and reports local. Do not commit or push anything to GitHub, create a PR, publish/deploy, or upload test artifacts. Do not copy credentials from chat into source, tests, reports or logs. Use configured secret storage and redact evidence. Do not repeat secret values in responses.

I have authorized local audit, fixes and testing. Continue ordinary reversible implementation without repeatedly asking permission. If required information is missing, ask a concise specific question and continue work that does not depend on the answer. Credentials alone do not identify a permitted phone destination. Use only an explicitly designated test number for live calls; do not contact arbitrary users, run a campaign against real customers or purchase resources. Keep production-impacting actions outside this local task.

Do not hide or remove an expected feature solely to make the checklist pass. Make it work; if an external prerequisite prevents live testing, explain the exact dependency and leave that acceptance item blocked. Do not invent credentials, successful calls, database results, screenshots or performance figures. Verify current provider protocols against official documentation when implementation depends on them.

## Reporting and completion

Maintain `IMPLEMENTATION_STATUS.md` with the current findings, files changed, test commands/results, live evidence, environment limits and next work. Update the page checklist and audit ledgers after each meaningful batch. Reports must distinguish fully reviewed files from scans and working components from end-to-end verified journeys.

Give concise progress updates explaining actual fixes, evidence and remaining work. At completion deliver a detailed final report, full file/page/provider matrices, a fresh-user end-to-end demonstration, billing reconciliation, latency/accuracy results, setup/runbook and any remaining limitations. Say the platform is fully working only when all requirements in the plan's definition of complete pass. If any required journey remains blocked or unverified, say so clearly and continue all independent authorized work.
