# Kodewaves client installation

This directory contains the source-free Compose deployment input for the
client edition. It is an implementation package, not an accepted production
installer: fresh-server install, upgrades, rollback, owner rotation and live
telephony acceptance remain open. Read
[`../../docs/deployment/client-installation-license.md`](../../docs/deployment/client-installation-license.md)
for the owner-issued license and security model.

The API image starts the API, ARQ worker and campaign orchestrator. This Compose
topology exposes only one API listener and has no nginx dispatcher, so client
images stay at one asynchronous FastAPI process even on hosts with more CPUs.
The Asterisk ARI manager remains disabled unless an installation enables it.

## Before installation

Kodewaves must provide the installation ID, signed license token, approved
API/UI/infrastructure image digests, and the signed release manifest for that
API image. The token must license the exact public hostname in `PUBLIC_HOST`.
If an IP allowlist is used, the owner checks the source IP it observes; setting
`TURN_HOST` or `SERVER_IP` does not establish that binding.

Prepare a Linux server with Python 3, Docker Engine and the Docker Compose plugin.
The installer preflight uses only Python's standard library and needs no pip
packages. Point
`PUBLIC_HOST` DNS at this server and allow inbound TCP ports 80/443, UDP 443,
TURN UDP/TCP 3478 and UDP media ports 49152–49200. The example `.env` enables
the bundled Caddy ingress profile by default; Caddy obtains and renews HTTPS
certificates, routes `/api/v1` to the API, `/voice-audio` to MinIO, and all
other web paths to the UI. Application, API and MinIO HTTP ports bind to
localhost; PostgreSQL and Redis have no host-published ports. If the server
already has an HTTPS proxy, clear `COMPOSE_PROFILES` in `.env` and configure
those same three routes there, preserving the original `Host` header.

The bundled Caddy service uses the fixed `CLIENT_CADDY_IPV4` address on the
`CLIENT_INTERNAL_SUBNET` network. `FORWARDED_ALLOW_IPS` must match that exact
address so Uvicorn accepts Caddy's forwarded HTTPS scheme and public host; the
installer preflight checks this pairing. This is required for provider webhook
signature checks that reconstruct the public HTTPS URL. If using an existing
proxy, set `FORWARDED_ALLOW_IPS` to the proxy peer address or narrow CIDR as
seen by the API container (often the Compose bridge gateway for a host proxy).
Do not use `*`; that would let any peer forge forwarded headers. Determine the
peer address from your Docker network and proxy setup before installation.

When `FORWARDED_ALLOW_IPS` is unset with bundled ingress, it defaults to
`CLIENT_CADDY_IPV4`, including a custom address. If you explicitly set both
values, keep them equal; preflight rejects a mismatch.

For an existing Caddy instance on the same host, the equivalent route block is:

```caddyfile
voice.customer.example.com {
  @api path /api/v1 /api/v1/*
  handle @api {
    reverse_proxy 127.0.0.1:8000
  }

  @audio path /voice-audio /voice-audio/*
  handle @audio {
    reverse_proxy 127.0.0.1:9000
  }

  handle {
    reverse_proxy 127.0.0.1:3010
  }
}
```

Replace the site name with the licensed `PUBLIC_HOST`. Keep both path prefixes
intact; the API also serves authenticated WebSocket routes under `/api/v1`.
Expose the configured TURN UDP/TCP ports directly to the Internet; HTTP proxying
does not carry WebRTC media traffic.

## Configure

1. Copy `.env.example` to `.env` in this directory.
2. Replace every `<...>` placeholder. Use immutable `image@sha256:...` references
   supplied by Kodewaves. If using bundled direct ingress, set
   `CLIENT_CADDY_IMAGE` to its approved digest; if using an existing proxy,
   leave it blank, clear `COMPOSE_PROFILES`, and set `FORWARDED_ALLOW_IPS` to
   that proxy's peer as seen by the API container. Do not use floating tags
   such as `latest` or wildcard proxy trust.
3. Generate fresh, unique secrets for this installation. `MASTER_CREDENTIAL_ENCRYPTION_KEY`
   must be a URL-safe-base64 encoding of 32 random bytes. Keep `.env` readable
   only by the installation operator and out of source control and backups that
   are not encrypted.
4. Put the signed manifest for the selected API image at
   `client-release-manifest.json` beside this Compose file, or update
   `CLIENT_RELEASE_MANIFEST_FILE` to its local path.
5. Verify the hostname, license, image digests and manifest all refer to the
   same approved release before starting services.

## Build and publish an owner-approved release

### CI image verification before an owner release

The GitHub Actions workflow **Verify client bundle images**
(`.github/workflows/client-bundle-verification.yml`) runs on pushes to
`codex/client-bundle-theme` and can also be dispatched manually. It runs the Docker boundary,
Caddy configuration, signed API/UI inventory, installer preflight, full Compose
interpolation checks, and a disposable API/UI runtime smoke without production
signing keys or registry publication. Select the reviewed branch and provide
the approved immutable Caddy image reference as its `caddy_image` input.

The same check runs on a Docker-capable Linux machine with Python,
`cryptography`, and SQLAlchemy 2.0.43 installed. SQLAlchemy is imported by the
release schema checker even when the check only reads migration files:

```bash
python deploy/client/ci_verify.py \
  --caddy-image registry.example.com/kodewaves/caddy@sha256:<approved-digest> \
  --report /tmp/client-verification.json
```

Temporary keys are generated outside the build context and removed afterward.
Only a successful run writes the report; an existing report path is rejected
to avoid confusing stale evidence with a new result. CI uploads only that
report, which records image IDs, ingress digest, signed-manifest hash, installer
preflight result, and the result of the actual `docker compose config --quiet`
command. On the Docker runner it also builds the repository's version-pinned
MinIO service image, starts API/UI with disposable Postgres, Redis and MinIO
dependencies, and checks API health, the UI root, and HTTP 402 for a protected
API request with an invalid license. A unique Compose project, loopback-only
ephemeral host ports, and an internal-only network isolate the smoke; the
Compose project volumes/network/containers and temporary MinIO image are
removed in `finally`. Postgres and Redis use immutable CI image digests. The
smoke's invalid license fails before any owner HTTP request, and the internal
network blocks egress. It does not prove an owner-enrolled installation or
owner alert delivery.

The report also records the protected API/UI inventory file counts and scan
durations measured while the build tool creates the signed release manifest.
These measurements make packaged integrity-hash cost visible for later startup
profiling; they do not by themselves measure API/UI startup latency. A report
is written only after those commands succeed; unit tests mock Docker and are
not themselves Docker/Compose execution evidence.
The check also renders a custom subnet with `docker compose config --format json`
and verifies that the API trusts the resulting Caddy address. Its report records
this separately as `custom_network_proxy_config`.
Images produced by this check use disposable trust keys and an invalid test
owner URL. They are verification artifacts and cannot serve as customer releases.
The runtime smoke is not full clean-install acceptance: owner enrollment, the
first-administrator journey, real domain/IP binding, updates/rollback, live
alerts, and browser/telephone acceptance remain separate release gates. The
next branch push or manual verification run executes this runtime smoke.

### Production release

On the Kodewaves release runner, use a registry namespace you control and
authenticate with that registry before using `--push`. Keep the private release
signing key outside the checkout and Docker build context. The public key passed
to `--release-public-key-file` must match the private signing key. Example:

```bash
python deploy/client/build_and_verify.py \
  --api-tag registry.example.com/kodewaves/client-api:2026.10.25 \
  --ui-tag registry.example.com/kodewaves/client-ui:2026.10.25 \
  --caddy-image registry.example.com/kodewaves/caddy@sha256:<caddy-digest> \
  --license-public-key-file /secure/owner/license-public.key \
  --release-public-key-file /secure/owner/release-public.key \
  --owner-status-url https://owner.example.com/api/v1/admin/client-installations/check \
  --owner-private-key /secure/owner/release-private.key \
  --manifest-output /secure/releases/client-release-manifest.json \
  --public-key-output /secure/owner/release-public.key \
  --push --release-env-output /secure/releases/release-images.env
```

The script builds both client images, verifies their owner-source and route
boundaries, validates the Caddyfile against the pinned Caddy image, and signs
the protected API/UI inventories with immutable image references and Alembic
compatibility metadata. In publish mode, it pushes first to resolve registry
digests, then writes `release-images.env` only after verifying the signed
manifest inside both images. Kodewaves must also provide approved pinned
digests for the infrastructure and Caddy images. Review the output and merge only its two
`CLIENT_*_IMAGE` values into the installer's `.env`; use approved immutable
digests for the infrastructure images as well. Copy the signed manifest into
the client install directory as `client-release-manifest.json`. Keep generated
release artifacts and key material out of source control. This host has not run
this Docker release flow.

By default, the manifest allows a fresh database or a database already at this
release's Alembic head. After testing an upgrade from a specific older revision,
add `--approved-upgrade-from <revision>` to the release command; repeat the
option for each tested origin. The builder rejects revisions outside the release
migration history before starting the image builds. Migration ancestry alone is
not evidence that a customer upgrade was tested. Rollback remains unapproved.

Example secret generation on a machine with Python 3:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Use the first command for password-like secrets and the second for
`MASTER_CREDENTIAL_ENCRYPTION_KEY`. Generate a different value for each
variable; do not reuse the example output or a secret from another installation.

### Package the customer installation

After image verification and release approval, prepare a file containing exactly
the seven approved `CLIENT_*_IMAGE` entries from `.env.example`. Copy the API/UI
digest values from the published release output; add approved PostgreSQL, Redis,
MinIO, coturn and Caddy digests. Do not include passwords, license tokens, private
keys or other configuration in this image-reference file.

```bash
python owner-tools/package_client_installer.py \
  --images-env /secure/releases/approved-images.env \
  --manifest /secure/releases/client-release-manifest.json \
  --release-public-key /secure/releases/release-public.key \
  --output /secure/releases/customer-installer.tar.gz
```

Run this owner-side command from the repository root. It verifies the release
signature, signed schema metadata and matching API/UI registry digests before
creating an archive. It refuses an existing output path and any unexpected
image-input keys, including secrets. The fixed delivery set contains a customer
installation guide, Compose/Caddy/preflight files, a pinned `.env.example`, the
signed manifest, public release key and file checksums. No application checkout,
owner build/signing tools, local `.env` or private keys are included.

Deliver the installation ID and license token separately. Send the archive's
SHA-256 through the trusted delivery channel so the recipient can authenticate
the downloaded package. The file checksums inside the archive detect accidental
file changes; they do not authenticate its sender. Packaging does not replace
image build, clean-install, owner-alert or upgrade/rollback acceptance.

## Start and create the first administrator

Run commands from this directory so Compose resolves `.env` and the manifest
path consistently. Validate the inputs before Docker contacts any registry or
starts the services. Complete mandatory owner enrollment in `INSTALL.md` before
starting client services. Use `compose_client.py` for every Compose command; it
pins the project name and always includes the persistent recovery overlay. It
adds the identity overlay automatically after enrollment:

```bash
python3 validate_install.py
python3 compose_client.py config --quiet
python3 compose_client.py pull
python3 compose_client.py up -d api
python3 compose_client.py ps
```

Wait until the API reports healthy and its logs contain
`Initial owner installation check succeeded`. Health alone does not mean the
owner has approved this installation yet. Startup runs database migrations and
verifies the owner-signed release manifest and license; the periodic owner
check also confirms revocation, integrity and optional source-IP policy. If the
check has not succeeded yet, wait for the poller and retry bootstrap. The
preflight checks local formatting, pinned images, hostname/IP shape, secret
strength, encryption key length and manifest presence; it does not replace
signed license/manifest verification by the API.

Client startup initializes shared catalog/template data but does not create
owner accounts, grant promotional wallet minutes, seed SaaS sale offers, or
download local inference models. The owner account-creation script is excluded
from the client image. Create the initial local administrator once, using the
licensed bootstrap below with a new empty installation database.

```bash
python3 compose_client.py run --rm --no-deps api \
  python -m api.services.bootstrap_client_admin --email admin@customer.example.com
```

The command prompts for the password interactively. It refuses to run after a
user or workspace already exists. Then start the UI and remaining services:

```bash
python3 compose_client.py up -d
python3 compose_client.py ps
```

Complete HTTPS/WSS proxy setup and check the public hostname before signing in.
Client administrators manage local users, workspaces and allowed branding from
Settings. License issuance, enabled features, limits and release control stay
with Kodewaves.

## Updates and recovery

Back up the database and persistent volumes before an update. Update the API and
UI image digests and install the matching newly signed release manifest as one
approved release, then recreate the services. Keep the previous image digests,
manifest and encrypted backup available for recovery. A rollback is safe only
when the previous application version supports the current database schema;
that compatibility has not yet been accepted across releases. For license
renewal, follow `INSTALL.md` to replace the token and recreate both the API and
UI before the handover window ends. A Compose restart does not reload changed
environment variables. Follow the license guide for key rotation, DNS changes
and owner outage behavior.

The bundle's `recovery.py backup-docker` command can stop the project, verify no
running container still writes the Postgres or MinIO volumes, and create a cold
archive. `recovery.py restore --docker-volumes` stages data into new labeled
volumes and keeps the original set available for rollback with
`recovery.py rollback-docker`. These Docker operations have deterministic
failure-path tests but have not been exercised against a Docker daemon; they
are not yet accepted restore evidence. See `INSTALL.md` for the required
maintenance commands and limitations. Use `compose_client.py` for every
Compose operation so the project name and active recovery volume mapping remain
consistent. Owner enrollment is required before starting services.

Do not expose `.env`, the signed license token, database credentials or the
release manifest through a public web server. A customer with root control of
the host can alter local software and disable local monitoring; the signed
manifest is detection and enforcement within the unmodified client package,
not unbypassable remote attestation.
