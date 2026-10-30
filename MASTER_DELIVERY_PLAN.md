# Kodewaves — single delivery plan

Updated 30 October 2026. This is the single execution checklist for the existing platform, commercial client bundle, shared voice flow, theme, and planned business expansion. The longer business and AI documents are specification references; this file owns current status, sequence, and acceptance. Status entries record observed evidence; they do not imply live acceptance.

## Verified checkpoint

- GitHub `main` is `8074fe81335f2b08a8cdc39a6c0d86b8f6527f91`, verified with `git ls-remote`. The other chat reports a source-only fast-forward from `c92462c9` containing 12 runtime/UI files, including the booking-license update and theme corrections. Its focused UI build generated all 52 pages; the live VPS has not been rechecked after this push.
- The latest GitHub Actions run for `main` (`41064519414`) failed at Release Please because the repository secret `RELEASE_PLEASE_TOKEN` is missing. This is a release-automation configuration issue, not a client-bundle verification result; no client-bundle workflow run exists for this feature branch yet.
- This worktree is `codex/client-bundle-theme` at `f2ee7f2b`, clean and synced with `origin/codex/client-bundle-theme`. Relative to fetched `origin/main`, the branches diverge: 45 main-only commits and 204 client-branch-only commits. This is ancestry, not missing-feature count. Preserve newer main security/runtime changes; do not bulk-merge or delete.
- A read-only UI audit confirms the public home, pricing, platform and deployment pages, shared theme/navigation, multiple workspace panels, and owner-console surfaces in this branch differ materially from `main`. Cohesive candidate UI commits include `fadf1680`, `f15b16b0`, `109c93a8`, and `72a9fa3d`; they still require integration review and acceptance on the release candidate.
- Current client-branch UI checks: `npx tsc --noEmit` passed; the focused appointment-template regression passed 2 tests after mapping its legacy blue accent to the emerald workspace palette in both template surfaces. The main branch already contains the runtime palette mapping per the other chat; this branch adds the regression test. Full client-branch build and browser visual acceptance remain open.
- The `c92462c9` UI baseline is now deployed: container `kodewaves_ui` runs `kodewaves-ui:release-c92462c9`, image `sha256:87862f7746d968476412a8df57d3f44a87b61394ef06cd5e4bd26cce31c15eb2`, is healthy, and local `/api/health` returned HTTP 200. This is not the newer client-branch theme/panel UI, so the user's visual redesign acceptance is still open.
- Last direct VPS verification was on `c92462c9`: UI and API containers were healthy. The currently running source/images after the `8074fe81` push are unverified; the other chat is inspecting production. Do not infer live theme acceptance from the successful source build.
- The integrated `codex/kodewaves-unified-work` worktree remains separate at `84543305`, with two uncommitted edits (`ui/src/app/page.tsx` and `api/tests/test_billing_invariants.py`) and no upstream. Its 157 API tests, 58 focused UI tests, TypeScript check and production UI build passed there, but that candidate is not the client-branch release and has not been published or deployed.
- The client branch contains the owner control plane, signed installation/license flow, domain binding, optional IP policy, integrity events, plan enforcement, package tooling and focused tests. Selected source-level tests passed in prior turns, including 12 integrity-queue tests and 37 booking tests (the latter reported by the other chat). These do not prove signed-image build, fresh/upgrade installation, alert delivery, rollback, or live acceptance.
- Theme and public/app visual acceptance remain open against the deployed image: public routes, all workspace/admin navigation, readable text/icons, saved branding after reload, and responsive layouts must be reviewed after successful image deployment.
- The client-bundle verification workflow is being enabled on this existing feature branch so its isolated PostgreSQL, package/image, licensing, UI, and recovery checks can run in hosted CI without consuming laptop RAM.
- Shared voice acceptance is still owned by the other chat: browser and inbound/outbound telephone tests across the supported languages, with repeats, cutoffs, overlap, voice/gender behavior, announcement/greeting delay, and speech-end-to-first-audio latency measured.
- The CRM/ERP/industry catalog and social/email/WhatsApp/website automation remain roadmap scope, not shipped functionality; no new business module is marked accepted.

## Execution sequence

1. Keep a single release owner and use GitHub `main` at `8074fe81` as the integration base. Recheck the VPS source/image before deployment; preserve the current running images and confirmed rollback tags.
2. Integrate the public site, shared theme/navigation, workspace panels and owner console from the client branch as reviewed cohesive changes. Do not replace newer main-based runtime, migration or security behavior.
3. Integrate the unique client acceptance workflow and tests plus safe runtime additions. Preserve main's `f0a1b2c3d4e5` and `f2a3b4c5d6e7` migration files, `validate_owner_private_key_path`, atomic workflow-run claim, and general conditional campaign update.
4. Integrate the voice branch's unique fixes on the same reviewed release candidate, resolving overlapping files once and running regression checks over the combined tree.
5. Reconcile Alembic heads and run disposable PostgreSQL, API, UI, package, signed-image, clean-install, populated-upgrade, rollback and recovery checks on the combined source.
6. Resolve the UI build resource failure with a measured low-memory build or hosted-runner image artifact. Build immutable API/UI images from the exact reviewed SHA; never point production tags at an unverified candidate.
7. Deploy those images to the existing VPS release checkout, retaining rollback images. Verify source SHA, image digests, routes, health, saved branding, owner/client separation and browser rendering.
8. Complete browser audio plus inbound/outbound telephone acceptance with the voice owner. Record language coverage, repeats, cutoffs, overlap, configured voice, announcement/greeting delay and speech-end-to-first-audio latency.
9. Only after GitHub, VPS, image and acceptance evidence agree, remove branches proven merged and unused by active worktrees, then create the single shared work branch requested by the user.

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
| GitHub and server source | GitHub `main` verified at `8074fe81`; VPS has not been rechecked after this update | Source-only push reports 12 runtime/UI files; booking-license and theme corrections included | Live image/source match is unverified |
| Client/theme branch | `codex/client-bundle-theme` at `f2ee7f2b`, pushed to its existing remote; 45 main-only and 204 client-only commits | Theme follow-up fixes appointment-template blue accents and adds regression coverage; semantic integration remains open | Not yet verified live; visual acceptance remains open |
| Client package/license | Most core installer, signer, licensing, owner-control, integrity and feature-gate runtime already matches main | Candidate additions: client verification workflow, focused tests/helpers, signed IP-denial/recovery check and bounded owner-status polling. Keep main's migrations, signing-key path validation and telephony atomic-update guards | Fresh install, populated upgrade/rollback, alert delivery and signed customer image acceptance remain open |
| Voice flow | Other chat is integrating reviewed booking and voice fixes into the source release | Combined regressions and exact voice-branch coverage still need confirmation | Browser, inbound/outbound and real audio acceptance not complete |
| VPS images | UI runs `kodewaves-ui:release-c92462c9` at `sha256:87862f7746d968476412a8df57d3f44a87b61394ef06cd5e4bd26cce31c15eb2`, healthy; `/api/health` is HTTP 200. API remains `tts-phrase-48-20261029`, healthy | UI baseline image built from `c92462c9`; resource-capped API build for the same revision is active | UI health is verified, but requested redesigned UI is not in this image; API release, theme integration and complete live acceptance remain pending |
| Branch cleanup/shared branch | Many historical branches remain; client branch includes overlapping voice/runtime history | Do not bulk-delete or merge by ancestry counts. Compare content, retain unique work, and wait for deployment/acceptance | Cleanup and creation of one shared branch are explicitly last |
| Business expansion | CRM/ERP/industry and email/social/WhatsApp/website automation remain in the roadmap | No new module integration was accepted in this release | End-to-end industry journeys are not accepted/shipped |

Specification references: BUSINESS_PLATFORM_EXPANSION_ROADMAP.md (catalog and rules), AI_PLATFORM_CONTROL_PLAN.md (shared assistant/action semantics), COMMERCIAL_CLIENT_BUNDLE_ROADMAP.md (historical evidence). This file owns delivery order and current status; old dated entries do not override current evidence.
