# Client installation license

> **Implementation status:** the client/server verification path and read-only
> settings status, owner issuance/revocation records and DNS challenge verification
> are implemented. Owner-issued one-time installation-key enrollment, the client
> enrollment CLI and read-only identity overlay are also implemented in code.
> Renewal and staged key rotation are supported in code, but customer-image
> enrollment, live key-rotation checks, complete worker/provider limits, pushed
> owner alerts and full upgrade acceptance remain unverified.
> Do not use this as a production sales or onboarding procedure yet.

## License fields

The Kodewaves owner signs an Ed25519 license containing:

- `edition`: must be `client`.
- `installation_id` and `customer_id`.
- `iat` and `exp`: Unix seconds for activation and expiry.
- `domains`: licensed public hostnames.
- `ip_ranges`: optional IPv4/IPv6 server addresses or CIDR ranges.
- `features`: signed grants checked for selected API and call-entry paths.
- `limits.max_concurrent_calls`: positive signed cap for new voice calls across the installation.
- Optional `limits.max_seats`, `limits.max_workspaces`, `limits.max_agents`, and `limits.max_campaigns` cap provisioned users, organizations, workflows, and campaigns across the installation. Creation checks serialize through PostgreSQL; live installation acceptance is still required.
- If set, `max_seats` and `max_workspaces` must each be at least one so the initial client administrator and workspace can be created. `max_agents` and `max_campaigns` may be zero to disable creation of those resources.

The client API image contains the owner license and release **public** verification
keys baked into the approved image. The client environment supplies only the
signed license token. Changing an environment variable cannot replace these
verification keys or switch the baked client edition to SaaS; an edition
mismatch fails the integrity startup check and is reported to the owner when
the owner endpoint is reachable. The image does not need the private signing keys. Store
those keys outside client repositories,
Docker build contexts, client images and volumes, and shared logs. Use the owner-only commands under
`owner-tools/` to create a keypair and issue a token. The owner API supports
renewal and staged key rotation; follow the live rollout sequence below and
verify it against the deployed owner and client versions before production use.

### Configure the owner signer in Docker Compose

The normal SaaS Compose stacks do not mount signing keys. On the **owner** host,
store the license private key as `current.key` in a dedicated absolute directory
outside the checkout and build context. The API image runs as UID/GID 10001;
grant that identity read access to this directory and its key files while keeping
them inaccessible to other users. For example, on a standard Linux Docker host,
use a root-owned directory with group 10001 and mode `0750`, and key files with
group 10001 and mode `0640`. Adapt this for rootless Docker or user namespaces.
Keep release-signing keys and all client installations out of this directory.

Set `KODEWAVES_OWNER_KEYS_DIR` to that host directory in the owner stack's
environment, then add `deploy/owner/docker-compose.owner.yaml` as a second
Compose file. For the repository's default SaaS stack, for example:

```bash
docker compose -f docker-compose.yaml -f deploy/owner/docker-compose.owner.yaml config
docker compose -f docker-compose.yaml -f deploy/owner/docker-compose.owner.yaml up -d api
```

The overlay binds the directory read-only into the owner API, sets the current
signer path, and passes the optional legacy signer paths and trusted proxy
CIDRs. Paths in `KODEWAVES_OWNER_LEGACY_LICENSE_SIGNING_KEY_FILES` are
colon-separated container paths under `/run/kodewaves-owner-keys`; for example,
`/run/kodewaves-owner-keys/old.key`. Use the same overlay with the chosen owner
SaaS Compose stack when upgrading, so recreation does not remove the mount.
The repository's `deploy.sh` adds it automatically when
`KODEWAVES_OWNER_KEYS_DIR` is set in the environment or root `.env`.
The customer installer does not include this overlay. Check that the API can
read the key and that issuance and a client check succeed before using it.

Before API issuance, the owner creates a challenge using
`POST /admin/client-installations/domain-challenges` with `customer_id` and
`domain`. The API returns a one-time TXT value for
`_kodewaves-verification.<domain>`. The customer publishes that value, then
the owner calls `POST /admin/client-installations/domain-challenges/verify`.
The owner API checks public DNS and records verification. Challenges expire
after 24 hours; a domain verification is accepted for issuance for 30 days.
The owner API must be able to reach its public DNS resolvers on port 53.
Creating a new challenge resets the previous verification for that customer
and domain. The owner panel provides these actions. DNS proof establishes
control at issuance; it does not prevent a host administrator from copying
software and changing local environment settings later.

The hosted owner API can issue and inventory installation records through
`/admin/client-installations`. It requires a Kodewaves superuser and an owner
signing key file configured with `KODEWAVES_OWNER_LICENSE_SIGNING_KEY_FILE`.
The API returns the token once; the database stores only its fingerprint and
entitlement metadata. A superuser can mark an installation revoked through
`POST /admin/client-installations/{installation_id}/revoke`, and the owner UI
shows that state. Online clients receive revocation through the periodic owner
check. A client that was previously verified can use the 24-hour outage grace
until the check resumes or grace expires, subject to license expiry.
The owner can renew an unrevoked installation with a freshly verified domain
through `POST /admin/client-installations/{installation_id}/renew` or the owner
panel. The replacement token is returned once. The prior token remains
registered for at most 48 hours, bounded by its original expiration, to allow
an operator to update the client environment. Another renewal is refused during
that handover. Before it ends, the operator must update the client `.env` and
recreate both API and UI containers as described in `deploy/client/INSTALL.md`.
Both consume the token; the UI uses it for integrity alerts. A Compose restart
alone does not reload a changed environment.

### Rotating the owner license key

1. Build and distribute a client API image with the new license public key as
   `--license-public-key-file` and the old key as
   `--legacy-license-public-key-file`. Keep the release verification key and
   signed manifest aligned with that exact image. Upgrade clients to this
   dual-trust image before giving them new-key tokens.
2. Copy the old private key to a protected legacy file and add its container
   path to `KODEWAVES_OWNER_LEGACY_LICENSE_SIGNING_KEY_FILES` (path-separated).
   Recreate the owner API with the overlay and verify old-token checks first.
   Prepare the new key in the same owner key directory, set its group and mode
   so UID/GID 10001 can read it, then atomically rename it to `current.key`.
   The key generator creates private files with restrictive permissions; adjust
   their group access before the rename. Owner status checks verify each bearer
   token and sign the reply with its matching key, so clients still pinned to
   the old key continue checking in.
3. Renew installations, install their new tokens on dual-trust client images,
   and wait for the old-token handovers to finish. Retire the old owner private
   key and publish an image without the old public key only after all clients
   have moved. Do not issue a new-key token to an old-key-only client image.
The owner exposes `POST /admin/client-installations/check` for a deployed
installation to present its signed bearer token and a fresh nonce. It returns
a short-lived, owner-signed status bound to that token, installation ID and
nonce. For licenses with `ip_ranges`, the owner compares the request source IP
it observes with those ranges and includes the result in the signed status.
An out-of-range source blocks new calls and data-plane requests without latching
permanent revocation; a later check from an allowed IP restores access. IP-bound
licenses require a fresh owner status and do not use the general 24-hour owner
outage grace for new calls. The
owner stores the most recently observed IP in installation inventory. Uvicorn
first processes forwarded headers only from peers listed in `FORWARDED_ALLOW_IPS`;
configure that setting to the actual ingress proxy or dedicated trusted network,
never `*`. If the application itself receives an unprocessed proxy chain, set
`KODEWAVES_OWNER_TRUSTED_PROXY_CIDRS` to the CIDRs of its actual reverse proxies
so the owner resolves that chain. Never list customer-controlled proxy ranges
in either setting. The client API polls every 60
seconds and caches verified status in shared Redis.
This observed address is the client's outbound egress IP as seen by the owner;
the Caddy/`FORWARDED_ALLOW_IPS` setting in the client install package controls
incoming forwarded headers for the client's own API and is a separate trust
boundary. It does not change the source IP of the outbound owner check.
An existing call is not ended by the poller. If the owner is unreachable, a
previously verified active status permits new calls for up to 24 hours after
the response expires; with no prior successful check, new calls are denied.
The owner's HTTPS check endpoint is baked into the approved image at release
time; the installer cannot redirect it through an environment variable. Other
feature boundaries and live renewal acceptance remain open.
The same background check re-verifies the signed protected-file manifest. A
detected mismatch denies new calls locally and is reported to the owner's
installation record. The owner panel shows the integrity alert and last check
time. This is a software-level signal: a customer with host control can disable
or replace local monitoring, so it cannot prove that customer-held code was
never changed. Each failed check sends a bounded reason, protected-component
path and expected/observed SHA-256 values where available. The owner stores a
deduplicated incident with first/last seen times and occurrence count; an
unacknowledged count appears in the owner sidebar. Acknowledgment does not
clear the client-side denial. Automated owner email/push alerts are not yet
connected.
If a protected-file check fails before a client service starts, that service
makes one bounded, best-effort report to the pinned owner endpoint before
exiting. The failed service still exits if the owner is unreachable; the owner
may then only see that the installation stopped checking in.

### Recovery after an integrity incident

An integrity failure permanently blocks that installation ID: the owner marks
its status revoked, renewal is refused, and acknowledging the incident only
records that an owner reviewed it. Replacing the files while keeping the same
installation ID does not clear the owner or client latch. Preserve the alert
and hashes as incident evidence. After investigation, build and verify a clean
approved release, then issue a replacement license with a new unique
installation ID (repeat the DNS challenge if domain verification has expired).
Install the matching API/UI image digests, signed release manifest, new
installation ID and new license token together. If the client host may have
been controlled, use a clean host and rotate any credentials that could have
been exposed; do not treat the old installation as trusted just because the
new image starts. Keep the prior owner record for audit.
Issuance rejects unknown feature names and requires `voice` plus a positive
`max_concurrent_calls` limit for calling. `campaigns` also requires `telephony`;
telephony, campaigns and widgets require voice. Licensed domains must be valid
DNS hostnames, without ports or URL paths.

## Client environment values

Set the following in the deployment environment before building/starting the
client edition:

```dotenv
KODEWAVES_EDITION=client
KODEWAVES_INSTALLATION_ID=<id matching the signed license>
KODEWAVES_LICENSE_TOKEN=<owner-signed license token>
PUBLIC_BASE_URL=https://<licensed-domain>
```

`ip_ranges` is checked against the source IP observed by the owner service, not
the client's `SERVER_IP` environment variable. If the owner is behind a reverse
proxy, configure `KODEWAVES_OWNER_TRUSTED_PROXY_CIDRS` on the owner deployment.

The client Compose package defaults `ENABLE_SIGNUP=false`. After starting the
services and letting the API finish migrations, create the first local
administrator once from an interactive terminal:

```bash
docker compose -f deploy/client/docker-compose.client.yaml run --rm --no-deps api \
  python -m api.services.bootstrap_client_admin --email admin@client.example.com
```

The command prompts for the password without placing it in shell history. It
requires the signed installation license and release manifest, refuses a second
bootstrap after any user or workspace exists, and creates the administrator,
first workspace and membership in one database transaction. API keys are created
later from the client administrator's **API Keys** page, which shows each raw
key only once; bootstrap does not create a hidden key whose secret cannot be
recovered.
Run it only against the intended new client database. The client administrator
can then create and select workspaces and create or suspend local users in the
Settings page. These paths apply the signed `max_workspaces` and `max_seats`
caps; public signup is disabled by the API for the client edition even if the
client changes `ENABLE_SIGNUP`. The client Compose file also pins it off. The
client administration screen has no
owner license, billing or release controls.

Build both API and UI images with `--build-arg KODEWAVES_EDITION=client`.
The UI build excludes `/admin` and `/superadmin` pages; the API build copies
filtered source that excludes owner route implementations. The API also omits
those route trees at startup. A standard `saas` image is not a client image.
Inspect the resulting image contents before distribution.
On a Docker-capable owner release runner, run `deploy/client/build_and_verify.py`
with owner key files, the pinned HTTPS status URL and registry-qualified API/UI
tags. With `--owner-private-key`, `--manifest-output`, and
`--public-key-output` together, it reads protected-file hashes from the built
API image, signs the exact API/UI inventories, embeds each image's immutable
registry digest plus the Alembic head and upgrade ancestry in the signed
payload, verifies the signer matches the release key baked into the image, and
runs both verifiers against that payload. Add
`--push --release-env-output <path>` to resolve and sign registry digests for
production. The push is required before the final signature because immutable
registry references are not known until then; the Compose environment file is
written only after both image verifiers accept the signed manifest. Keep the
private key on the owner release runner, outside the build context. The Docker
build, inspection, signing and publish flow has not yet run on this Windows
worktree because Docker is unavailable.

Before publishing the client API image, the owner signs a release manifest for
the exact files in that image through `deploy/client/build_and_verify.py`, which
uses `owner-tools/sign_client_release.py` on the API and UI image inventories.
Supply that manifest through
`CLIENT_RELEASE_MANIFEST_FILE` in the client
Compose package at `deploy/client/docker-compose.client.yaml`; the public key is
already in both images. Set
`CLIENT_API_IMAGE` and `CLIENT_UI_IMAGE` to pinned client image digests. The
manifest public key is separate from the license public key. API, worker,
telephony and migration entrypoints verify the protected Python and service
scripts before starting. The UI verifies its compiled server, static assets,
public assets, runtime script and baked trust data before serving, then repeats
the check every minute; a mismatch stops the UI and sends an owner alert. A
missing manifest, invalid signature or changed protected file stops the
affected process. The manifest must be regenerated and re-signed for every
approved release.

The client Compose file is standalone: it does not extend the development
stack, build from source, or mount a source checkout. Supply approved digest
references for API, UI, pgvector, Redis, MinIO, Coturn and, when enabled, Caddy.
The example environment enables the bundled Caddy HTTPS ingress, which routes
`/api/v1` to the API, `/voice-audio` to MinIO and other paths to the UI. Point
the licensed hostname at the server and expose ports 80/443 for HTTPS
certificate issuance, plus TURN UDP/TCP and media ports for WebRTC. Installations
with an existing ingress can clear `COMPOSE_PROFILES` and configure the same
routes while preserving the original `Host` header. API and MinIO HTTP ports
bind only to localhost. Keep database, Redis, MinIO and application secrets in
a restricted installation environment file. The API and UI containers run with
read-only root filesystems, all Linux capabilities dropped, and
`no-new-privileges` enabled. `/tmp` is ephemeral; Next.js receives an ephemeral
image-cache mount, and API-derived audio is held in the `api_audio_cache`
Docker volume at `/app/kodewaves_pcm_cache` (owned by API UID/GID 10001). The
derived caches may be cleared and will be rebuilt; they are not customer source
or canonical uploaded recordings. These mounts still need validation in the
actual Docker images. The bundle relies on separately configured model/provider
endpoints and has not passed a fresh-server install, upgrade or rollback
acceptance test.

The API validates the token, edition, installation ID, expiry and configured
public domain for HTTP and WebSocket data plane requests. Protected HTTP and
WebSocket requests must include exactly one valid `Host` header whose hostname
matches the signed license domain; the reverse proxy must preserve the incoming
host when forwarding to the API. The installation's `PUBLIC_BASE_URL` or
`PUBLIC_HOST` remains checked for background license validation. Owner-signed status
enforces optional source IP ranges using the address observed by the owner;
`SERVER_IP` is not an authority for that check. `/health` and `/installation/license` remain available to
show recovery status; the status endpoint requires an authenticated client
administrator and never returns the signed token. An active WebSocket session is not forcibly terminated
when a license expires mid-call; the next connection is refused.

Authenticated client users can call `GET /installation/features` to retrieve
the validity state and enabled feature names needed by workspace navigation.
This response omits installation IDs, customer IDs, domains and IP ranges.
The client UI hides unlicensed modules and blocks direct module pages; API
feature middleware remains the enforcement boundary.

A client administrator may edit customer-facing name, tagline, logo and
favicon URLs, support email, primary color and font from Settings. These values are stored separately from
the signed license and applied to the client public page, sign-in branding and
app navigation. The API validates the color and logo URL; client branding
cannot change installation identity, feature grants or limits.

Selected voice, telephony, campaign, CRM, appointment, form, knowledge-base,
widget and billing API paths require their corresponding signed feature. New
calls require the appropriate voice/source grants and a positive
`max_concurrent_calls` limit. Call admission applies the installation-wide cap
atomically in Redis alongside the organization limit. A missing grant or limit
denies new actions. The API middleware also checks cached, signed owner status
on client data-plane requests. Revocation, an integrity latch, an unchecked
installation, or exhausted outage grace blocks those requests; health, login,
branding read and license diagnostics remain available.

Workflow model catalog, tools, credentials, prompts, folders, node specs,
TURN credentials, call reports and usage routes require the voice grant. Signed
S3 URLs and metadata are gated by key namespace: campaign objects require
`campaigns`, knowledge-base objects require `knowledge_base`, and recordings or
other workflow artifacts require `voice`.

## Current limits

The client root administrator controls its own machine and can patch local
software. A signed license can deter accidental reuse and catch configuration
mismatches, but this local verifier cannot provide unbypassable anti-tamper
protection. API-path feature checks, the new-call concurrency cap, and optional
provisioned seat/workspace/agent/campaign caps are only part of the entitlement
surface.
Worker jobs, providers, usage totals and other numeric limits still need runtime
enforcement and integration tests. The creation caps also need live PostgreSQL
verification.
The Redis concurrency integration tests also require a running Redis service;
they have not been verified in this Windows worktree.
Release verification runs at startup and cannot protect against an operator
who controls the client host replacing both the verifier and its entrypoint.
The periodic owner check and in-app incident alerts exist, but pushed alerts
and independent remote attestation do not. The Compose
package is a packaging input, not an accepted production installation.
The owner can compare the observed egress IP with a licensed range, but
independent network attestation remains unavailable. The enrollment protocol,
owner API and client CLI exist, but enrollment from a clean customer installation
and recovery have not passed acceptance. Renewal and staged key rotation are
implemented but require live multi-version acceptance. Production rollout and
rollback are also unverified.
