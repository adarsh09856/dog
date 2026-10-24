# Kodewaves client bundle and owner control plane plan

Updated 24 October 2026. This is a design and implementation plan; none of the licensing or tamper controls below is claimed to exist yet. The other chat owns the self-hosted voice flow and broad platform fixes. This workstream covers theme, public pages, commercial packaging, client installation and owner control.

## Product boundary

There are two products:

1. **Kodewaves SaaS** runs on Kodewaves infrastructure. The Kodewaves owner operates the superadmin control plane, sets tenant plans, credentials, model access and limits. Customers use the ordinary organization/user application.
2. **Kodewaves client installation** runs an agreed data-plane bundle on a client's server or cloud account. The client administers its own users, agents, calls, telephony, CRM and allowed branding. Kodewaves alone operates the owner control plane, issues licenses, enables features and controls releases. The client bundle contains no owner superadmin UI, owner private keys or master licensing secrets.

Do not call the client's administrator a superadmin. Use clear roles: **Kodewaves owner**, **client administrator** and **client user**. Enforce the distinction in API authorization, not just hidden navigation.

## A. Full visual theme and public-site change

Current source evidence: `ui/src/app/globals.css` has shared light/dark tokens; `ui/src/components/ThemeSwitcher.tsx` toggles a local browser preference. `ui/src/app/page.tsx` and `ui/src/app/pricing/page.tsx` contain hard-coded marketing/model copy. `ui/src/app/admin/layout.tsx` and `ui/src/app/superadmin/layout.tsx` expose owner navigation in the general app build. `api/routes/admin/settings.py` stores company name, logo, support email and primary color. Legacy Dograh identifiers remain for compatibility in model configuration and auth cookies.

1. Define a Kodewaves design system: type scale, spacing, cards, charts, call controls, status colors, responsive layouts and light/dark variants. Replace remaining Dograh visual language and obsolete screenshots/wordmarks across public, auth, user and admin pages. Preserve protocol or data aliases only where migration requires them.
2. Rebuild public home, pricing, product/features, docs entry, login/signup and error pages from one theme. Marketing claims and pricing must come from the current supported product/catalog, not hard-coded model names or unverified latency/language claims.
3. Separate **platform brand** from permitted **client brand**. The client can configure logo, public colors, fonts, contact links, domain and customer-facing copy within validated tokens. These settings must apply to their public pages and user panel without altering executable code.
4. Visual acceptance: desktop/mobile, light/dark, public/auth/user/admin, keyboard contrast/focus, localization, no broken links or stale Dograh references. Capture screenshots and verify the deployed UI.

## B. Commercial packages and owner-controlled plans

1. Keep SaaS subscriptions, wallet minutes and credit bundles as owner-managed products. Add a separate **installation license** product for a client deployment. Installation entitlement records features, seats/workspaces, concurrency, usage policy, support/update window and permitted deployment count. Do not mix a client installation license with SaaS credit bundles.
2. Owner control plane manages client accounts, installations, licenses, domains, observed IPs, feature grants, release channels, billing, alerts and revocation. Client UI shows its own entitlement and usage but cannot edit the license or owner plan.
3. Existing plan/bundle gaps in `reports/platform-audit/2026-10-23-follow-up.md` (persisted overage/public/popularity behavior and pricing controls) must be reconciled before selling them as effective limits. Enforce each entitlement in the API/job/telephony runtime and test at the boundary.
4. Keep local inference, cloud/BYOK, telephony and data residency as explicit feature flags or policy choices. A plan label alone must not imply a working provider or guaranteed latency.

## C. Client installation and license binding

1. Publish versioned API/UI/worker/media-service images to a private registry, with a signed release manifest listing image digests, schema version and compatibility. Client installs with a small documented Compose/Helm package and config file; no source checkout or owner secrets are required.
2. Kodewaves owner issues a short-lived, one-time enrollment token for a named client. The installer generates a deployment key pair locally and submits its public key plus installation ID. The owner verifies domain control with a DNS challenge and records the approved FQDN. Bind the license to the installation key and approved domain(s); use observed public IP/CIDR allowlisting where a stable egress IP exists.
3. Use signed license documents verified with an embedded **public** key. Check installation ID, domain, optional IP range, product edition, features, validity and release entitlement on the server side. Store the private signing key only in the owner control plane. Provide key rotation and renewal.
4. Installation settings page shows license status, bound domain/IP, edition, enabled features, expiration/renewal and last owner check. Client administrators can view this information and request a domain/IP change; only the owner can approve a binding change.
5. Use a mutual-authenticated heartbeat to the owner service for revocation, release status and alert delivery. Support a documented outage grace period and offline policy if the product is sold for disconnected deployment. Do not abruptly terminate an active call when a check fails; refuse new licensed actions after the grace period and show a clear error/status.
6. Provide a recovery process for DNS, IP, server and certificate rotation. Dynamic IP, NAT, proxy/CDN and disaster recovery make IP-only locking brittle; domain plus installation identity is primary, IP allowlisting is an optional additional control.

## D. Integrity, modification alerts and realistic enforcement

1. Sign release manifests and pin OCI image digests. On startup and periodically, the client-side verifier checks approved component digests and reports a mismatch with installation ID, component, expected/observed digest and timestamp. Owner dashboard receives a rate-limited alert; client sees **“This installation contains unapproved component changes. Contact Kodewaves support.”** The alert must not include secrets or call content.
2. Separate customizable **configuration/assets** from protected executable components. A client may change approved branding and ordinary user-facing content through settings without triggering an integrity failure. They cannot change API, worker, authorization, billing, license or owner-control code within a supported installation.
3. If protected code fails verification, block new privileged/licensed operations after a safe grace window and expose health/support information. Preserve data export and recovery access; avoid breaking an in-progress call. Log the reason in both local audit and owner control plane. Test normal upgrades and rollback so they are not flagged as tampering.
4. **Security limit:** a client who has root/admin control of its own server can patch or replace any local verifier, remove its network connection, extract container layers or bypass a local shutdown. Bundling, bytecode, minification or game-style asset packing can raise casual-copying cost but cannot guarantee code secrecy or enforce “site stops if changed.” For strong control, keep licensing, proprietary policy decisions and any non-distributable core service on infrastructure Kodewaves operates, with the client installation calling that service. If offline full-code operation is required, rely on signed releases, contractual terms and detection rather than an absolute anti-tamper promise.

## E. Repository boundaries and migrations

- Split owner-only routes/pages from deployable client pages at build and API route registration. Owner superadmin accounts and license signing material must never ship in a client bundle. Audit existing `/admin` and `/superadmin` naming, `is_superuser` checks and backend route dependencies.
- Add migrations for installation identity, license metadata, allowed domains/IPs, enrollment, heartbeats and integrity events. Tenant client data stays in the client database; owner service keeps only licensing/telemetry metadata needed for control.
- Refactor branding, public page copy and plan display to read validated configuration. Retire Dograh branding safely without breaking legacy saved provider modes or auth migrations.
- Define exact feature enforcement points in FastAPI, workers and telephony admission, with UI reflecting server policy. The UI must not be the enforcement boundary.

## Delivery order and acceptance

| Phase | Deliverable | Acceptance evidence |
|---|---|---|
| 1 | Owner/client role and package specification; threat model; plan/feature matrix | Reviewed routes and data fields; explicit SaaS versus client-install boundaries. |
| 2 | Kodewaves theme and public-site rebuild | Screenshots and navigation/accessibility checks across public, auth, user and admin surfaces. |
| 3 | Owner license service and client enrollment | Two isolated installations; valid, expired, revoked, wrong-domain and wrong-IP cases; key rotation. |
| 4 | Signed images and integrity reports | Modified image/config tests; approved branding change passes, protected component change alerts and blocks new actions safely. |
| 5 | Commercial plans and client UI | Owner grants/revokes limits; client sees accurate entitlement but cannot edit it; real API/worker limits enforced. |
| 6 | Install, upgrade, rollback and recovery | Fresh client server, DNS/IP change, temporary owner outage, migration and rollback tested end to end. |

## Current status

Planning only. The existing SaaS app has some branding and admin controls; it does **not** yet implement an owner-issued installation license, domain/IP binding, signed bundle integrity, owner alerting on component modifications or a clean client-only distribution. Do not market those as available until phases 1–6 pass.
