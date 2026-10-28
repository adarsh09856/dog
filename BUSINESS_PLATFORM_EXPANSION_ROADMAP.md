# Kodewaves business platform expansion roadmap

Status: planning, 27 October 2026. This is an expanded product direction, not a claim that the listed capabilities exist. Keep the current client-bundle work in `codex/client-bundle-theme` and the voice work in its separate checkout. The user has stopped merging. Do not switch, reset, merge, or deploy either checkout until that instruction changes.

## Product direction

The [AI platform control plan](AI_PLATFORM_CONTROL_PLAN.md) defines the shared assistant, action permissions, approval and recovery path, complete module coverage, delivery order and acceptance checklist. All new business panels and integrations must use that action contract so the assistant can operate the delivered platform consistently.

Build a configurable business operating platform with voice AI, omnichannel communications, customer relationships, workflow automation and optional industry modules. Support the owner-operated SaaS and a separately packaged customer installation. Customers enable only relevant modules, configure their workspace and connect their own accounts; the owner controls plans, licensing, limits and availability. Design for multiple languages and accessibility, with capabilities determined by the connected model and provider.

Do not promise every industry, jurisdiction, social feature, device-linking method or model language until the specific journey is implemented and accepted. Rank opportunities with customer evidence, delivery cost, provider access and maintenance capacity. This catalog is broad rather than exhaustive.

## Current starting point and open release gates

Repository inspection shows existing CRM, appointments, widgets and campaigns screens and backend routes; their presence is not proof of complete business journeys. The current commercial roadmap records implemented branding, plan and client-license work alongside outstanding installation, payment, browser, phone and integration acceptance. Voice work belongs to the other chat. The existing platform must not be replaced by this roadmap or assumed ready for sale. See `COMMERCIAL_CLIENT_BUNDLE_ROADMAP.md` for its evidence and current gates.

## Shared platform capabilities

1. **Workspace and administration:** organizations, branches, teams, users, granular roles, invitations, activity logs, custom fields, localization, time zones, accessibility and configurable branding. Owner panel controls module availability, usage, license, support access and audit; client admins manage their permitted workspace.
2. **Customer and relationship data:** contacts, companies, identity matching and explicit merge review, consent and preferences, tags, ownership, custom objects, attachments, notes, activities and a chronological timeline. Every record and lookup is tenant-scoped.
3. **Unified conversations:** inbox for connected channels, assignment, queues, internal notes, SLA timers, status, search, handoff, attachments and AI summaries. Preserve original channel events and delivery status; never silently merge identities across organizations.
4. **Workflow automation:** visual trigger/condition/action builder with versioning, draft/test/publish, delays, schedules, loops with bounds, branching, human approvals, idempotency, retry/dead-letter queues, replay controls and an execution history. AI actions inherit user and tenant permissions and require confirmation for consequential operations.
5. **Knowledge and AI:** tenant-owned documents, retrieval permissions, citations where available, configurable agents and human escalation; voice and text reuse business tools without bypassing authorization. Measure speech-end to first audio, cold/warm behavior, interruptions and completion. Support provider-advertised languages without implying universal model coverage.
6. **Reporting and operations:** dashboards, funnel and service metrics, channel delivery, call quality, automation failures, export, scheduled reports, alerting, backup and restore. Define data freshness and metric semantics.
7. **Integration framework:** connection inventory, OAuth or provider-supported authentication, encrypted credentials, least privilege, webhook verification, secret rotation, rate limits, per-tenant isolation, idempotency, subscription renewal and reconnect flows. Provide API, signed webhooks and documented SDK/embed methods.
8. **Commercial control:** plan catalog, transparent pricing, module entitlements, resource and usage limits, trials, upgrades, expiry, payment reconciliation and invoices. Enforce at API, worker and action boundaries in both SaaS and client editions.

## Channels and automation

| Channel | Planned customer journey | Constraints / release evidence |
|---|---|---|
| Voice | Inbound/outbound phone and browser voice, transfer, recording, transcript, scheduling and follow-up. | Verify supported STT/TTS languages, latency, consent, interruption and routing with real browser and approved calls. |
| WhatsApp | Connect a business number, inbound inbox, approved templates, media, replies, handoff, delivery and opted-in campaigns. | Prefer official supported onboarding. Investigate QR linking separately with provider documentation and account policies; do not claim ordinary consumer QR login is officially supported. Test template approval, rate limits, opt-out and reconnect. |
| Email | Connect Gmail, Microsoft 365 or another supported mailbox; receive, route, draft, send, follow up, and track replies in the timeline. | Scope permissions, mailbox ownership, subscription renewal, duplicate delivery and unsubscribe; support reconnect without exposing credentials. |
| Facebook / Messenger / Instagram | Connect eligible business accounts and pages; handle supported inbox, comments, lead forms and publishing. | Confirm each permission, approval, account type and operation against current provider documentation before implementation. Do not assume feature parity across providers. |
| YouTube | Connect channel and manage supported comments, moderation and content workflows. | Verify OAuth scopes, quotas, allowed operations and provider approval; do not promise private messaging. |
| Other social / messaging | Evaluate LinkedIn, Telegram, SMS, RCS, web chat and region-specific channels against demand and official APIs. | Each adapter needs documented permissions, supported operations, pricing and a tested lifecycle; unsupported channels are labeled unavailable. |
| Website | Install a branded chat/voice widget, inquiry and lead forms, appointment booking, knowledge search and support entry on customer sites. | Domain allowlist, CORS, token scope/expiry, accessibility, spam protection, mobile behavior, CSP, data consent and a real third-party website test. |
| Ecommerce / marketplaces | Connect store, order, catalog, shipment and returns events to service and sales workflows. | Verify provider capability and tenant ownership; confirm actions before altering orders or issuing refunds. |

Example journey: a visitor submits a website inquiry → a tenant-scoped lead and conversation are created → a rule assigns the lead and sends an opted-in response → an agent schedules an appointment after confirmation → staff see the entire timeline. Duplicate webhooks must not create duplicate leads or send duplicate messages.

## Business functions and industry opportunities

| Area | Candidate workflows and panels | Dependencies and boundaries |
|---|---|---|
| Sales / CRM | Leads, companies, deal stages, activities, quotes, forecasts, routing, follow-ups and source attribution. | Shared contacts, inbox, automation, roles and audit. |
| Support / service desk | Tickets, shared inbox, priorities, SLAs, knowledge base, escalation, satisfaction and service reporting. | Channel adapters, knowledge permissions, schedules and reporting. |
| Commerce / retail | Catalog, stock visibility, orders, payments, delivery, returns, loyalty and customer support. | Store integrations, tax/payment design and approval for refunds. |
| ERP / distribution | Products, warehouses, stock movements, procurement, suppliers, purchase and sales orders, invoices and accounting exports. | Reliable inventory ledger, concurrency, tax/accounting integration and migration strategy. |
| Clinic / dental / allied health | Patient intake, staff calendars, appointments, reminders, billing, follow-ups and referrals. | Separate sensitive-data permissions, consent, retention, local legal review, clinician oversight and audit; no unsupported diagnostic claims. |
| Hospitality / travel | Property or reservation inquiry, bookings, availability, guest communication and service requests. | Calendar and property/channel-management integration; cancellation and payment policies. |
| Restaurants / food | Reservations, menus, inquiries, catering orders, pickup/delivery status and customer feedback. | POS/order integrations, business hours, allergy escalation and confirmation. |
| Education / training | Admissions, inquiries, student contact, classes, attendance, fee reminders and parent communication. | Guardian permissions, safeguarding, calendar and education-system integration. |
| Real estate / property | Leads, listings, property matching, visits, tenancy inquiries and maintenance tickets. | Listing feeds, schedules, document security and consent. |
| Professional services / agencies | Leads, consultations, projects, time, proposals, tasks, billing and client portal. | Project/accounting integrations and client-level access. |
| Field service / home services | Requests, estimates, dispatch, technician schedules, jobs, parts and service follow-up. | Location, mobile access, inventory and proof of completion. |
| Automotive | Vehicle/customer records, test drives, service booking, repair status and reminders. | Dealer/service integrations and scheduling. |
| Manufacturing / wholesale | B2B inquiries, quotes, order status, procurement, inventory and service issues. | ERP integration and approval for price/stock commitments. |
| Finance / insurance | Lead and appointment workflows, document collection, service requests and human handoff. | Jurisdiction-specific review, sensitive-data controls and no unapproved financial advice. |
| Logistics / transport | Shipment inquiries, status, exceptions, dispatch, proof of delivery and returns. | Carrier integrations, tracking-event validation and customer identity controls. |
| Recruitment / HR | Candidate inquiries, interviews, applicant communications, internal requests and onboarding. | Candidate privacy, consent, role restrictions and human decision-making. |
| Nonprofit / public services | Intake, case routing, events, donor/member communications and multilingual support. | Accessibility, sensitive records, eligibility and local policy review. |
| Wellness / beauty / fitness | Bookings, memberships, staff schedules, reminders, service history and payments. | Calendar, payment, consent and cancellation policy. |

Industry modules should be assembled from shared primitives plus explicit domain extensions, rather than separate disconnected copies. A vertical is considered supported only after a real user can complete its core journey, including failure recovery and tenant isolation.

## Delivery sequence and acceptance

0. **Protect and finish current work:** preserve both checkouts and server changes; complete client image verification, clean installation, license/integrity tests, billing and branding acceptance. The merge stays stopped per user instruction. Voice browser and telephone acceptance remain owned by the other workstream.
1. **Discovery and architecture:** inventory existing routes, schemas and UI; map customer journeys and gaps; define module contracts, tenant data ownership, roles, provider capability matrix, resource budgets, migration and deployment design. Select first target industry using customer evidence; do not assume a market priority is already approved.
2. **Foundation:** deliver tenant-safe contacts, conversations, roles, audit, event ingestion and resilient automation execution. Verify duplicate events, concurrent updates, cross-tenant access, backups and upgrade paths.
3. **CRM and website journey:** connect a third-party site form/widget to lead capture, assignment, staff reply and timeline. Test anonymous abuse, delivery failures, consent and mobile accessibility.
4. **First channel and shared inbox:** implement an officially supported business messaging connection and email integration; prove onboarding, permissions, inbound/outbound, disconnect, renewal, opt-out and recovery with test accounts and provider-approved flows.
5. **Automation and AI actions:** implement configurable triggers/actions and human handoff, then prove an end-to-end inquiry-to-appointment journey without duplicates. Confirm consequential actions; verify voice and text use the same tenant-scoped business state.
6. **First vertical:** ship one complete, selected business workflow with real users, operational reporting, import/export, billing and documented support. Only add medical or regulated capabilities after applicable review.
7. **Additional verticals and channels:** expand from measured demand using the catalog above, with provider-specific acceptance and independent module entitlements. Avoid claiming broad channel support from one successful adapter.
8. **Commercial acceptance:** verify owner/client edition separation, licensing and revocation, plan downgrade, audit, recovery, observability, load and capacity on representative 4-core/8-16 GB hosts as well as larger deployments. Publish tested requirements rather than assumed hardware guarantees.
9. **Integration and release:** only after the user lifts the merge hold, obtain a stable core voice checkpoint, integrate in a separate checkout preserving both sides, resolve conflicts, run migrations and targeted/full checks, stage and test the complete combined revision, and document rollback before any production release.

## Provider and legal research checkpoints

- [Microsoft Graph Outlook change notifications](https://learn.microsoft.com/en-us/graph/outlook-change-notifications-overview): mailbox subscriptions need appropriate permission and lifecycle handling.
- [YouTube comment API guidance](https://developers.google.com/youtube/v3/guides/implementation/comments): comment actions and moderation require supported operations and authorization.
- Obtain and record current official Meta/WhatsApp onboarding, messaging and account policies before specifying a QR or embedded-signup experience. Provider API access, pricing and review are release dependencies, not assumptions.
- Before regulated deployments, identify the actual markets, data types, hosting arrangements and applicable requirements with qualified local counsel; a generic checklist does not establish compliance.

## Tracking and decision record

For each module record: owner, priority, chosen customer journey, scope exclusions, dependencies, provider permissions, design, migrations, implementation, automated tests, real integration tests, accessibility, security, documentation, pricing and release evidence. Use states `proposed`, `designed`, `implemented`, `verified`, `accepted`; never call an idea complete because a panel exists. Keep the current release tracker authoritative for existing work and record expansion decisions here.
