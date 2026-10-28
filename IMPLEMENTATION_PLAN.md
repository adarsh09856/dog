# Platform completion plan

User requirements confirmed: 2026-10-07. Implementation is now authorized; the earlier audit is a baseline, not a completion certificate.

## Required product behavior

1. An administrator enables cloud credentials/models and local engines. Users see only enabled, accessible capabilities; disabled/missing credentials never silently route to another vendor.
2. Authorized users can configure BYOK. STT, LLM and TTS can be independently selected from permitted cloud/local sources. Voice, language, model identity and credential source survive save, test, publish and execution.
3. Billing derives from server-resolved sources and prices for the actual configuration, including mixed configurations. Client flags cannot waive charges; receipts cannot create unearned credits; duplicate completion does not charge twice.
4. Users configure a telephone provider and numbers, assign an agent, and successfully test both browser and telephone calls. Inbound routing, callbacks, transfers and hangup must authenticate and bind to the correct organization and call.
5. Published agents run campaigns with correct scheduling, capacity, retries and terminal states. Incoming calls and agent tools connect to bookings and CRM. Transcripts, recordings, dispositions, logs and usage are consistent.
6. Every user/admin page handles loading, errors and permissions accurately. Admin model management and emergency call termination perform the action they claim.

## Implementation sequence and acceptance evidence

| Work package | Required changes | Acceptance evidence | Status |
|---|---|---|---|
| 1. Configuration and catalog | Selected organization, admin visibility, exact model routing, BYOK/local policy, source attribution, voice/language preservation | Unit/contract tests for cloud-only, local-only, BYOK and mixed layers; disable/revoke cases | In progress |
| 2. Runtime adapters | Provider construction errors, audio buffering/rates, local service contracts and dependency availability | Constructor regressions, audio contract tests, synthetic local round trip | In progress; selected local contracts tested, live round trip pending |
| 3. Billing and payments | Persist trusted resolution, atomic debit/replay protection, authenticated receipt reconciliation | Mixed-source charging, forged context/receipt, replay and concurrent completion tests against test DB | Pending |
| 4. Telephony and web calls | Setup/readiness, authenticated callbacks, atomic admission, real hangup and reliable transfers | Browser call plus authorized live incoming/outgoing/transfer calls for configured carriers | Pending |
| 5. Campaigns and integrations | Published-agent preflight, retries, capacity, CRM/booking writeback, tenant isolation | Test-DB journeys for campaign lifecycle and tools; live provider evidence separately | Pending |
| 6. User/admin completeness | Page-by-page CRUD and error handling, catalog selection, settings, logs and truthful monitoring | Typecheck, UI tests and authenticated browser journeys for each page | In progress; browser acceptance pending |
| 7. Deployment and performance | Migrations, worker synchronization, operational setup, accuracy and latency | Clean test deployment, measured cold/warm/concurrent call results and documented hardware | Pending |

## Execution rules

- Preserve pre-existing working-tree edits. Implement focused changes with regression coverage; keep this plan and the audit updated.
- Backend database tests must load `api/.env.test`, never development/production credentials. No real purchases or unsolicited messages.
- Do not equate catalog visibility with provider conformance, a direct model response with a working call, or a single synthetic clip with measured accuracy.
- Live acceptance requires configured provider credentials, routable callback URLs, test numbers and authenticated browser access. Document missing prerequisites and continue independent implementation.
- Every package remains pending until its own acceptance evidence exists. The platform is complete only when all packages pass; neither a source scan nor this plan establishes completion.

## Baseline

See `reports/audit-2026-10-07/REPORT.md`, `TELEPHONY_CONTINUATION.md` and `MANUAL_REVIEW_PROGRESS.md` for known findings and exact review limits. Existing source changes at implementation start include admin settings/monitoring, user routes, resolver, quota service, workflow DTO and common URL utilities; these must not be overwritten wholesale.
## Requirements reconciled from follow-ups — October 20, 2026

The full platform scope above remains mandatory. Speech work is first priority, not a replacement for page/function acceptance:
- CPU-only self-hosted STT, LLM and TTS; all 22 scheduled Indian languages, Indian English and natural code-switching. Verify each layer's actual coverage independently; do not label unsupported languages available or silently switch to cloud.
- Immediate configured greeting; accurate original-language transcripts; follow-up context, correct tool use, interruption recovery, no repeat greetings or invented results; measured 700–800 ms target rather than assumed benchmark claims.
- Clear natural male/female speech with matching first-person grammar, stable voice identity and no clipped words/unnatural gaps, in web and telephone.
- Template and custom agents must work for multiple business services, not only booking. Model/voice/language/settings choices must persist across creation, editing, test, publish, campaigns, widgets and telephone.
- Every listed page includes all its actions, settings, permissions, persistence and background effects. New regular users must not obtain administrative access or private information.
- Preserve independent branding, customizable installation/region settings, tenant isolation, existing custom code and unrelated VPS sites. No hardcoded production hostname or single workflow as the only working path.
- Remove explicitly retired model/image/cache artifacts only after checking active dependencies; keep storage/resource evidence. No unnecessary local inference installs, paid diagnostic calls or repeated broad test runs.
- Keep evidence and unresolved gaps explicit; do not claim a full platform from component tests. Tests, diagnostic scripts and reports stay unpushed.
