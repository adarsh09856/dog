# Kodewaves — single delivery plan

Updated 30 October 2026. This is the single execution checklist for the existing platform, commercial client bundle, shared voice flow, theme, and planned business expansion. The longer business and AI documents are specification references; this file owns current status, sequence, and acceptance. Keep this tracker local unless the user asks to publish it.

## Verified checkpoint

- GitHub `main` was last confirmed at `8a44d2b03f93eb72e99f922f7a363deb87730dfc`; no remote update has been made in this local-first pass. Candidate typecheck, `docker compose --profile local config --services`, and `git diff --check` passed before that source checkpoint was pushed. It is not deployed to the live containers.
- Local consolidation worktree: branch `main`, `139e3084`, 359 commits ahead of `origin/main`. The active merge currently has `MERGE_HEAD=0c370767` (`codex/platform-completion`), no unresolved index entries, and no staged tree changes relative to `139e3084`; it is not committed. This is an older 70-commit source ref and is not the exact voice input the user scoped. Review semantic deltas before concluding it.
- Actual app/compose checkout for the running containers was last confirmed at `/root/kodewaves-merge-20261029`, branch `codex/platform-completion-20261030`, commit `2511131b`, with image tags `kodewaves-api:tts-phrase-48-20261029` and `kodewaves-ui:candidate-theme-polish`; source/image parity remains unverified. The separate `/www/wwwroot/default/app.kodewaves.in` checkout was `codex/production-integration` at `35ae46d3` with 76 dirty entries and is not the compose source path. No VPS change has been made.
- The exact user-scoped inputs remain the actual VPS branch `codex/production-integration`, this chat's `codex/client-bundle-theme`, and the other chat's `codex/client-voice-integration`. The local voice branch tip is `1ebe61d2`; it has three unique product commits relative to the current local consolidation candidate (language preference, duplicate-turn/failed-TTS handling, and isolated integration checks). It is not yet merged into local `main`.
- Client worktree: local `codex/client-bundle-theme` at `ea0a1b92`, 79 commits ahead of its tracking ref. Do not merge the branch wholesale: it diverges substantially and replaces/removes newer main-based public pages and panel work. Select and reconcile client lifecycle/release files against the current local candidate.
- Focused UI evidence: earlier runs passed 26 tests on the local form/theme patch and 14 tests on public pricing/platform/deployment pages; scoped ESLint passed. Those runs do not prove all panels or live image parity. The form fix already exists on GitHub `main` through `7f12a018`; do not duplicate it.
- Image build for `8a44d2b0` has not run. Release Please failed because its required token input was unset (run `41046611562`); the older build for `a9111252` failed at registry login (run `41038551883`). No matching images have been published and no live image tag has changed.
- Core owner controls, signed license, domain/IP binding, integrity checks, alerts and feature enforcement exist in the local client candidate, but production acceptance remains open. This worktree has the release builder, image verifier, install/recovery tests, and a locally revised CI workflow. The workflow now retains the full focused API/PostgreSQL, UI, install/recovery, licensing, migration, and disposable-image checks; it removes persisted verification artifacts and uses no registry push. Its 30 focused test-path references were confirmed present in the current local consolidation tree. It has not yet been merged, run on hosted CI, or verified against a signed client image.
- Focused UI evidence: 26 tests passed across eight files on the local form/theme patch; an additional run passed 14 tests across the public pricing, platform and deployment pages. Scoped ESLint and `git diff --check` passed on the UI patch. The form-fix source is already present on GitHub `main` through commit `7f12a018`; do not cherry-pick the duplicate local commit `57d20ee4`. Live image/source parity remains unverified.
- Image build for `8a44d2b0` has not run. The `Release Please` workflow for this main push failed because its required `token` input is unset: [run 41046611562](https://github.com/adarsh09856/dog/actions/runs/41046611562). The older image build for `a9111252` also failed at DockerHub login: [run 41038551883](https://github.com/adarsh09856/dog/actions/runs/41038551883). No matching images have been published and no live image tag has changed.
- Core client license, identity, owner-only controls, IP/domain binding, integrity checks, alerts and entitlement runtime are already represented on `main`. The shared candidate adds `deploy/client/build_and_verify.py`, `ci_verify.py` and `verify_images.py`; these are not integrated on `main` yet. A focused local change correcting the verifier workflow trigger/job-condition mismatch is verified in the client worktree and has been sent to the integration owner to port onto the candidate. Keep it out of the release until present and reviewed there.
- `main` at `8a44d2b0` contains staged-tag digest promotion with final-tag overwrite protection and the stronger disposable owner enrollment/check acceptance flow. The client verifier workflow is still absent from `main`; a main-compatible, source-only workflow is drafted locally and passed YAML/static checks. It invokes only `scripts/check_alembic_single_head.py` and `deploy/client/ci_verify.py`, creates no persisted artifact, and never publishes release tags. Main/PR runs require the approved `CLIENT_CADDY_IMAGE` repo variable; manual dispatch accepts the digest directly. The workflow has not yet been copied into the local main-based integration tree or pushed. No package/image runtime acceptance has run. Documented clean-install, populated upgrade/rollback, owner-alert and live browser/telephone gates remain open.
- Full commercial acceptance remains open: signed package build, fresh customer install, domain/TLS and optional IP binding, owner alert delivery, feature enforcement, tamper rejection, populated-data upgrade, rollback and restore.
- Voice acceptance remains with the other chat: browser and telephone behavior in Hindi, English and Hinglish; no repetition, cutoff or overlap; configured voice; inbound/outbound calls; and measured speech-end-to-first-audio latency.
- The user reports that the redesigned UI is not visible live. A healthy UI container does not prove theme deployment; public pages, workspace/admin panels, branding persistence, navigation and responsive rendering require review against the exact integrated image.
- CRM/ERP/industry panels, social/email/WhatsApp automation and website-to-business workflows remain specified roadmap scope; no new business module is marked shipped.

## Execution sequence

1. Keep all remotes and live containers unchanged. Use one local integration owner; preserve dirty checkouts and rollback images while this worktree handles only the isolated client-release track.
2. Reconcile the client public/app theme and client-release changes against local `main`; the form fix `57d20ee4` already exists on GitHub `main` as `7f12a018`, so do not duplicate it.
3. Review and integrate the client release builder, image verifier, full focused test workflow, disposable installation/recovery checks and owner-alert path. Exclude whole-branch changes that regress newer source or migrations.
4. Reconcile Alembic heads and schema behavior on disposable PostgreSQL; run API, UI, package, signed-image, clean-install and recovery checks on the combined source.
5. Build immutable API/UI images from the reviewed SHA. The current hosted build failed at registry login. Do not publish a test build as `latest`.
6. Deploy the same accepted source and images to the existing VPS checkout, retaining current images for rollback. Verify source SHA, image digests, routes, health, saved branding and owner/client separation.
7. Complete browser-audio and inbound/outbound telephone acceptance with the voice owner. Record language coverage, repeats, cutoffs, overlap, configured voice, announcement/greeting delay and measured end-to-end latency.
8. Remove only branches proven merged and unused by any active worktree, after GitHub and VPS match the accepted release.

## Problem → correction → proof

| Problem | Correction | Required proof |
|---|---|---|
| VPS is still on an older source/image than GitHub `main` | Deploy the reviewed combined SHA to the existing release checkout | VPS checkout SHA, API/UI image digests, healthy services and live route/version smoke |
| Hosted image build fails at DockerHub login | Repair registry credentials or use the approved configured registry | Successful API and UI architecture jobs with immutable tags/digests |
| Client branch mixes useful work with stale/destructive history | Integrate reviewed file groups; preserve current main behavior | Combined diff review, migration graph, API/UI regressions |
| Client release verifier and installation smoke are missing from `main` | Review/integrate the builder, image verifier and disposable install/recovery CI | Green hosted package workflow using signed images and a disposable migrated database |
| New theme/copy is not visible in the live UI | Include the current page/form fixes and deploy the matching UI image | Browser review of public, workspace and admin routes, saved-brand reload, responsive layout |
| Voice calls still need fluent and reliable behavior | Voice owner finishes its isolated fixes and accepts them with real audio/calls | Browser plus inbound/outbound call evidence, supported-language coverage and latency measurements |

## 01 — Establish and integrate the current combined baseline

Owner: both chats; integration coordinator maintains the release candidate. Status: in progress.

- [x] Record GitHub `main`, VPS source/image state, client branch and current UI verification.
- [ ] Integrate the exact voice checkpoint `codex/client-voice-integration` at `1ebe61d2`; do not substitute the older platform-completion ref or duplicate voice-file edits.
- [x] Confirm the scoped form fix is already in GitHub `main` as `7f12a018`; no duplicate cherry-pick needed.
- [ ] Import the full client package verification workflow and test support into the local candidate, retaining current main migrations and runtime behavior.
- [ ] Reconcile the combined Alembic graph on disposable PostgreSQL; verify clean install and upgrade paths.
- [ ] Review combined diff, source-to-image provenance, rollback images and one deployment owner before release.

Gate: one reproducible candidate preserves newer voice and client behavior. Local tests or health on an old image do not close this step.


## 02 — Complete shared voice and grounded conversation

Owner: voice chat. Depends on 01 for combined acceptance; implementation proceeds now. Status: implementing.

- [ ] Instrument speech end, endpointing/STT completion, LLM first usable text, first synthesized audio and first caller-audible audio. Report cold/warm, median/p95 and concurrent-load results; do not substitute LLM first-token time for total delay.
- [ ] Fix utterance splitting, missed/duplicate recognition, microphone lifecycle and premature endpointing. Preserve names, phone numbers, dates and code switching.
- [ ] Preserve conversation state and agent purpose across follow-ups; retrieve only permitted tenant knowledge, call connected tools, and acknowledge missing information. Never claim saved/booked/sent actions without a durable successful result.
- [ ] Stream coherent TTS phrases without truncation, duplicate playback, overlap or self-triggered interruptions. Apply supported voice/language/gender settings consistently; label unavailable capabilities honestly.
- [ ] Exercise different custom agents and arbitrary follow-ups, not only cached greetings. Cover Hindi, English, Hinglish and the other actual supported languages, including language changes mid-conversation.
- [ ] Measure against the requested 1–1.5 second speech-end-to-first-audio target. Record CPU/GPU/provider limits and unresolved failures; do not claim the target universally when evidence fails.
- [ ] Browser first: conversation grounding, mic recovery, interruption, reconnect, tool results and silence behavior. Then use the same services for inbound/outbound; distinguish carrier announcement delay from bot greeting delay.
- [ ] After browser passes, call the user-authorized number 6366458170 and coordinate inbound acceptance on the attached Twilio number. Record caller feedback and measured latency.
- [ ] Expose new business actions through the same typed, tenant-scoped action layer used by text and UI, preserving permission and plan checks.

Gate: accepted browser and telephone journeys with audio evidence, correct state changes, supported-language matrix and measured latency. Merge each independently verified fix promptly; release only after combined checks.

## 03 — Finish complete public and application design

Owner: this chat. Depends on 01 for live acceptance. Status: implemented in parts; acceptance open.

- [ ] Review public home, platform, deployment, pricing, login/signup; workspace navigation, overview, agent list/editor/test panel, campaigns, models, telephony, tools, files/recordings, CRM, appointments, forms/widgets, templates, usage/reports, wallet and settings.
- [ ] Review owner/admin dashboards, users, plans, credit packages, model catalog/settings, installation licensing, alerts, audit and monitoring.
- [ ] Deliver one professional layout system: hierarchy, spacing, typography, tables/forms, navigation, responsive panels, empty/loading/error states, dark/light themes, keyboard focus and restrained reduced-motion-aware transitions. A palette swap alone does not close this step.
- [ ] Save company name, logo, tagline and brand settings through admin; verify persistence and refresh across public/user/admin surfaces, including browser title/icon where supported.
- [ ] Verify every menu target, responsive overflow, authenticated/public routing and meaningful actions. Remove unavailable placeholders or finish their behavior; do not advertise simulated testing as available if it is not.
- [ ] Use the requested design references only after checking their actual contents/license; record what was applied. Do not claim a skill/repo was used without evidence.

Gate: screenshots and real create/edit/save/reload journeys on the accepted build at desktop/mobile sizes, not just component tests. Merge completed page groups with their shared dependencies and preserve current voice components.

## 04 — Commercial authority, pricing and plan enforcement

Owner: this chat. Status: substantial implementation; end-to-end acceptance open.

- [ ] Owner-only control plane manages plans/prices, provider availability, module grants, limits, customers, licenses, revocation and audited support access.
- [ ] Customer edition excludes owner routes/source and signing secrets; client admins manage permitted users/workspaces only. Verify denied escalation and cross-tenant access through APIs and background jobs.
- [ ] Public pricing derives from saved catalog values and valid currency/minute/seat/agent limits. Unknown prices show unavailable, not fabricated defaults. Checkout verifies provider events, handles duplicate callbacks and preserves ledger consistency.
- [ ] Enforce entitlements and limits at API, scheduled/queued jobs, AI tool actions and call dispatch. Test trial/expiry, downgrade, disabled modules, wallet policy and missing-plan fail-closed behavior.
- [ ] Verify real saved-brand, plan change, purchase/renewal and cancellation journeys in an authorized provider test environment; do not spend cloud-model keys for blanket tests.

Gate: unauthorized operations fail, permitted customer journeys persist, pricing and payment states reconcile. Merge API/schema/UI changes together with migration checks.

## 05 — Signed customer installation and owner control

Owner: this chat. Depends on 04. Status: local implementation and lifecycle verification; customer acceptance open.

- [ ] Produce API/UI bundle without owner control-plane code or secrets; sign protected inventories, immutable image references and approved schema upgrade origins.
- [ ] Verify clean install, domain DNS challenge, enrolled installation identity, optional observed-IP policy, signed status refresh, bounded offline grace, renewal/rebinding and revocation.
- [ ] Tamper approved protected files and verify startup/runtime rejection, useful customer-facing unavailable state, persisted owner alert and alert acknowledgment/reopening.
  - Local progress: periodic owner checks retain a detected finding in Redis across a failed or invalid owner response and retry it after connectivity returns; 12 focused owner-status tests passed on 2026-10-30. This change is uncommitted in the client worktree and is not in the current release image. Startup reporting and real outage/restart acceptance remain open.
- [ ] Test allowed branding/content customization without opening protected permission/licensing logic to edits. Document that host-root control prevents an absolute unmodifiable-code guarantee.
- [ ] Verify actual customer hostname, TLS and reverse-proxy behavior; bootstrap the first admin once, then enforce workspace/seat limits.
- [ ] Verify encrypted/access-controlled backups of configuration, identity and data; perform restore into new volumes, service/data checks, upgrade and rollback preserving compatible DB state.
- [ ] Publish only signed verified release digests; apply immutable registry policy and record any partial promotion. Deliver installer/operator instructions and tested resource requirements.

Gate: real signed install, owner communication, tamper, renewal, upgrade and restore/rollback evidence on isolated infrastructure. A selected-table PostgreSQL test or healthy API alone is insufficient.

## 06 — Accept and release the existing product foundation

Owner: both chats. Depends on 01–05. Status: pending.

- [ ] Run combined user/admin/customer-edition journeys and capacity checks at supported 4-core/8–16 GB resource profiles; publish measured limits and model requirements.
- [ ] Review release diff and migrations; take backup and rollback checkpoint; coordinate one deploy owner and a quiet call window.
- [ ] Merge the accepted candidate into main, update GitHub and VPS to the same source, deploy matching images, then confirm live pages, version, health and representative journeys.
- [ ] Tick accepted items with source/image IDs and evidence. Leave failed cases open and correct them; no invented overall percentage.

Gate: existing product is accepted live. Expansion design can advance beforehand, but incomplete base behavior must remain visible.

## 07 — Shared business and AI action foundation

Owner: this chat/business implementation; voice chat reviews voice compatibility. Depends on 06 for release. Status: planned.

- [ ] Inventory and reuse existing domain services. Define tenant/branch/team/record ownership, custom fields, schema versions, contacts/companies and explicit deduplication review.
- [ ] Implement durable event ingestion, identities, conversations/timeline, tasks, audit and role-scoped knowledge retrieval.
- [ ] Define typed action schemas: operation, actor/workspace, target, expected version, preconditions, confirmation policy, idempotency key, result and recovery state.
- [ ] Use identical authorization/business logic for panel, voice, text assistant and automation. AI previews consequential changes and reports persisted results; it cannot approve its own restricted actions.
- [ ] Guided business setup creates a reviewable configuration; users can change terminology, modules, forms, calendars, roles and workflows inside owner grants without code edits.

Gate: denied cross-tenant/role actions, duplicate-event handling, concurrent updates and a real UI/text/voice action all behave consistently. Merge foundation in coherent schema/API/UI increments.

## 08 — First complete website-to-business journey

Owner: business implementation. Depends on 07. Status: planned.

- [ ] Customer website form/chat/voice embed: verified origin, scoped public token, consent, abuse limits, accessible mobile behavior and branding.
- [ ] Inquiry creates lead/contact and conversation, assigns staff, records response, checks calendar capacity, confirms appointment and updates the shared timeline.
- [ ] Support custom fields, validation, spam failure, duplicate submission, unavailable staff/calendar, reschedule/cancel and staff handoff.

Gate: actual third-party-site journey through UI, API and business state; no duplicate leads/messages/bookings. Merge and release the complete journey before expanding channels.

## 09 — Shared inbox and channel connections

Owner: business/integration implementation. Depends on 07–08. Status: planned.

- [ ] Implement shared queues, assignment, internal notes, media, delivery status, customer identity review, consent and SLA escalation.
- [ ] Deliver provider-supported WhatsApp Business onboarding and email connections with OAuth/account identity, scoped encrypted credentials, webhook verification, renewal, reconnect and disconnect. Evaluate QR only for officially supported account flows.
- [ ] Add supported Facebook/Messenger/Instagram inbox/comment/lead/publishing actions; YouTube comments/moderation/content actions; SMS, Telegram, RCS, LinkedIn and other channels as provider capability and demand permit.
- [ ] Every connector defines exact operations, permissions, account eligibility, rate/quota behavior, costs, event deduplication, retry/dead-letter path and retention.

Gate per connector: onboard → receive → route → authorized reply/action → delivered/failed receipt → reconnect/revoke. One connector passing never marks all social integrations done. Merge each accepted adapter separately.

## 10 — Automation, sales and service operations

Owner: business implementation. Depends on 07–09. Status: planned.

- [ ] Versioned trigger/condition/action builder, schedules/delays, bounded branches/loops, drafts/test/publish, approvals, timeouts, retries and execution history.
- [ ] CRM pipelines, lead assignment, opportunities, versioned quotes/proposals, tasks, follow-ups and handoff from won work.
- [ ] Service tickets, business-hours SLA timers, projects/milestones, staff/resource calendars, booking capacity, reminders and waitlists.
- [ ] Reports with documented metrics, time zones, data freshness, scoped export and operational exception inbox.

Gate: inquiry-to-sale and inquiry-to-service journeys with duplicate/concurrent/provider-failure recovery; AI uses actual action results. Merge one accepted journey at a time.

## 11 — ERP and transactional modules

Owner: business implementation. Depends on 07 and 10. Status: planned.

- [ ] Catalog/services, price lists, orders, fulfillment, returns and refunds with verified payment state and explicit approvals.
- [ ] Inventory movement ledger, atomic reservations, units, locations, lot/serial/expiry, procurement/suppliers, receiving, work orders and quality holds.
- [ ] Invoices/subscriptions, expenses, payment reconciliation and accounting-system connectors; define jurisdiction/currency/tax requirements before claiming compliance.
- [ ] Project/time/resource operations, assets, dispatch/fleet, member/recurring-service and partner operations as entitled modules.

Gate: realistic order/procure/fulfill/return and project/invoice journeys; no overselling, duplicate charges or silent state corruption. Merge and accept each complete module independently.

## 12 — Configurable industries and additional channels

Owner: business implementation. Depends on relevant shared modules. Status: planned.

- [ ] Profiles cover appointment services, sales/B2B/SaaS, support/BPO, clinic/dental/allied health, pharmacy/labs, wellness/fitness, retail/ecommerce/marketplaces, restaurants/catering, hospitality/travel/events, education/campus/childcare, real estate/property/construction, legal/accounting/professional services, manufacturing/wholesale/distribution, logistics/fleet/rental/repair, home services, agriculture, nonprofit/community/membership, IT/MSP/security, publishing/media and further customer-defined combinations.
- [ ] Each profile defines records, relationships, fields, states, roles, calendars, panels, reports, connected systems, automation, permitted AI actions and exception handling. Industry names alone are not features.
- [ ] Preserve the full expanded catalog in BUSINESS_PLATFORM_EXPANSION_ROADMAP.md as a specification appendix. A tenant may combine profiles; no separate hard-coded assistant or permission system per industry.
- [ ] Sensitive medical, financial, legal, child or safety-related work requires defined permissions, retention and qualified human decision ownership before release.

Gate per profile: guided setup without code, one complete core customer journey, saved customization, denied unauthorized action, duplicate/recovery checks, export/audit and accessibility. Merge each accepted profile pack; do not claim every business is supported from sample panels.

## 13 — Continuous release and owner operations

Owner: both workstreams. Depends on each delivered increment. Status: planned.

- [ ] Per-module plan grants, metering/cost, model/provider language capability and capacity reporting remain truthful.
- [ ] Operate backups/restore drills, errors/alerts, tenant isolation audits, API/connector version upgrades and rollback procedures.
- [ ] Update the checklist after each accepted increment with commit, evidence, integrated revision, deployed images and remaining failures. Keep planned modules distinct from sold capabilities.

## Integration ledger

| Increment | Source evidence | Integration | Live acceptance |
|---|---|---|---|
| GitHub source candidate | `main` last confirmed at `8a44d2b0`; local-only consolidation is `main` at `139e3084` with an active merge state | No push in the current local-first pass | Not deployed to VPS |
| Active local merge | `MERGE_HEAD=0c370767` (`codex/platform-completion`), conflicts resolved but merge uncommitted; index tree currently equals `139e3084` | Review whether source content changed; this is not the exact voice branch requested | Do not publish until exact scoped inputs are represented and verified |
| Client release staging | Local client worktree `ea0a1b92`; release builder, image verifier and install/recovery tests exist; full focused workflow is restored locally | Workflow and master plan have uncommitted local edits; 30 referenced test paths exist in the local candidate | CLI import and Alembic single-head check pass; signed image/install acceptance remains open |
| Client lifecycle | Earlier isolated checks covered selected owner/license lifecycle paths | Current combined migration and full hosted workflow pending | Fresh install, populated upgrade, rollback, alert delivery and recovery pending |
| Client public/app UI | Earlier focused runs passed 26 local form/theme tests and 14 public pricing/platform/deployment tests; scoped ESLint passed | Fix already exists in GitHub `main` as `7f12a018`; live image parity is unverified | Live screenshots, saved-brand reload, all-panel navigation and responsive review pending |
| VPS runtime | Last confirmed Compose checkout `2511131b`; API/UI tags `tts-phrase-48-20261029` / `candidate-theme-polish` | No server update in the current local-first pass | Source/image parity and live UI/voice acceptance pending |
| Voice and business expansion | Exact voice branch `codex/client-voice-integration` at `1ebe61d2` has three unique product commits against the local candidate; business modules remain specified roadmap scope | Voice branch not yet integrated; active stale-platform merge must not substitute for it | Browser/telephone voice acceptance and each end-to-end business journey pending |

Specification references: BUSINESS_PLATFORM_EXPANSION_ROADMAP.md (catalog and rules), AI_PLATFORM_CONTROL_PLAN.md (shared assistant/action semantics), COMMERCIAL_CLIENT_BUNDLE_ROADMAP.md (historical evidence). This file owns delivery order and current status; old dated entries do not override current evidence.
