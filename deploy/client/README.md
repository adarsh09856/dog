# Kodewaves client installation

This directory contains source for the client-edition Compose deployment. For
customer deployment, use the exact Kodewaves-issued installer archive together
with its detached signature and independently supplied trusted release public
key. Verify the archive before extracting it, then follow [`INSTALL.md`](INSTALL.md).
Do not install from an unverified source checkout or treat disposable CI
acceptance as a production-signed customer release. Read
[`../../docs/deployment/client-installation-license.md`](../../docs/deployment/client-installation-license.md)
for the owner-issued license and security model.

The API image starts the API, ARQ worker and campaign orchestrator. This Compose
topology exposes only one API listener and has no nginx dispatcher, so client
images stay at one asynchronous FastAPI process even on hosts with more CPUs.
The Asterisk ARI manager remains disabled unless an installation enables it.

## Capacity planning

The default Compose CPU and memory limits are **ceilings**, not reserved
capacity, minimum hardware requirements, or a performance guarantee. With the
sample's bundled Caddy ingress enabled, the seven app services have ceilings
that sum to about **4.75 CPU cores and 4.75 GiB of memory**. Without bundled
Caddy, the six remaining services sum to about **4.5 CPU cores and 4.5 GiB**.
The host also needs capacity for Linux, Docker, filesystem cache and other
services. On a 4-core host, busy containers can contend because their combined
CPU ceilings exceed four cores.

The default client package uses connected or separately hosted inference. An
owner-approved package may also include the optional self-hosted profile with
Ollama, multilingual STT and VITS/Indus TTS images. That profile requires all
four model-image digests and `COMPOSE_PROFILES=direct-ingress,self-hosted`.
Budget at least 16 GiB RAM plus model-download storage; use connected inference
on an 8 GiB host. These are capacity guidelines, not certified latency or
concurrency targets. Test the selected models and expected call volume before
production; no 4-core/8-GB or 16-GB performance configuration is certified.

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
   Existing encrypted provider settings require the matching key at startup. For
   rotation, set the new key as `MASTER_CREDENTIAL_ENCRYPTION_KEY` and the old
   key in `MASTER_CREDENTIAL_ENCRYPTION_KEY_PREVIOUS`; re-save provider settings
   and run the supported workflow model-configuration migration before removing
   the old key. Installer upgrades preserve older JWT-derived keys in a
   `legacy-b64:<base64url-encoded UTF-8 secret>` decrypt-only entry when a new
   master key is generated. Keep a protected database backup until the migration
   is accepted.
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
API request with an invalid license. The acceptance run also starts a temporary
HTTPS owner peer, enrolls a disposable installation identity with the packaged
API helper, verifies signed owner status, and exercises first-admin bootstrap
and replay rejection against the running image. A unique Compose project,
loopback-only ephemeral host ports, and an internal-only network isolate the
smoke; the Compose project volumes/network/containers and temporary MinIO image
are removed in `finally`. Postgres and Redis use immutable CI image digests.
The temporary peer and signing material are test-only; this does not prove
production owner alert delivery, customer DNS/IP binding, or upgrade/rollback.

The report also records the protected API/UI inventory file counts and scan
durations measured while the build tool creates the signed release manifest.
These measurements make packaged integrity-hash cost visible for later startup
profiling; they do not by themselves measure API/UI startup latency. A report
is written only after those commands succeed; unit tests mock Docker and are
not themselves Docker/Compose execution evidence.
The check also renders a custom subnet with `docker compose config --format json`
and verifies that the API trusts the resulting Caddy address. Its report records
this separately as `custom_network_proxy_config`.
Images produced by this check use disposable trust keys and a temporary test
owner peer. They are verification artifacts and cannot serve as customer
releases. The runtime smoke covers test-host owner enrollment, signed status,
and first-administrator bootstrap; real customer domain/IP binding,
updates/rollback, production alert delivery, and browser/telephone acceptance
remain separate release gates. The workflow must complete successfully before
the disposable acceptance evidence can be treated as verified.

### Production release

On the Kodewaves release runner, use a registry namespace you control and
authenticate with that registry before using `--push`. Keep the private release
signing key outside the checkout and Docker build context. The public key passed
to `--release-public-key-file` must match the private signing key. Example:

The owner repository also includes the manual workflow
`.github/workflows/client-production-release.yml`. Before using it, configure a
GitHub environment named `client-production` with `main` as its only allowed
deployment branch and required human reviewers. The workflow uses an ephemeral GitHub-hosted `ubuntu-24.04` runner; no persistent or self-hosted signing runner is needed. The workflow fails closed unless it runs from `main` and the dispatch
confirmation is exactly `RELEASE`.

The separate Release Please automation also requires the repository secret `RELEASE_PLEASE_TOKEN`; without it, automated release preparation fails.

The workflow is pinned to `ghcr.io` and this repository's `kodewaves-api` and
`kodewaves-ui` package paths; it does not accept a registry hostname or package
path from the dispatch form. The job-scoped `GITHUB_TOKEN` authenticates the
release runner. Store these values as secrets in that environment:
`CLIENT_LICENSE_PUBLIC_KEY_B64`,
`CLIENT_RELEASE_PUBLIC_KEY_B64`, and `CLIENT_RELEASE_PRIVATE_KEY_B64`. The
private-key secret is the URL-safe Base64 encoding of the 32 raw private-key
bytes; it is written only to the runner's `/dev/shm` key directory for the
release and is removed when the step exits. The signed installer, manifest,
public key, and immutable image references are uploaded as a 30-day GitHub
Actions artifact. This workflow does not deploy to the VPS or publish an
unverified final image tag; the builder may leave temporary `kodewaves-verify-*`
staging tags in the registry for later retention-policy cleanup.

Create this release-signing keypair once on a trusted owner machine. Keep the
private key backed up offline and never copy it into the repository or an image
build context. Choose new file names for intentional rotation; the command
refuses to overwrite either output.

```bash
python owner-tools/generate_client_release_keypair.py \
  --private-key /secure/owner/release-private.key \
  --public-key /secure/owner/release-public.key
```

This signing key is separate from the license-issuer keypair. Back up both
securely and keep the matching public keys with the release configuration.

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

The script first checks that the requested release tags are unused. It builds
both client images, verifies their owner-source and route boundaries, and
pushes each to a unique `kodewaves-verify-<run-id>-<component>` staging tag to obtain
immutable registry digests. It signs the protected API/UI inventories and
Alembic compatibility metadata, verifies the signed manifest inside both images,
and runs the startup tamper-rejection checks. Only then does Docker Buildx
promote those exact verified digests to the requested release tags; the script
rechecks that each tag is unused immediately before promotion and confirms
that final tags resolve to the signed digests before it atomically writes
`release-images.env`. Use unique version tags and enable immutable-tag policy
in the registry: Docker Buildx does not provide a registry-portable
compare-and-swap operation, so another publisher could race between the check
and tag write. Failed verification leaves final tags and the output env file
untouched; a failure during the two-tag promotion may leave one verified final
tag published, but withholds the env file. Unique staging tags may remain in
the registry for later retention-policy cleanup. Docker Buildx is required for
promotion.

Kodewaves must also provide approved pinned digests for the infrastructure and
Caddy images. Review the output and merge only its two `CLIENT_*_IMAGE` values
into the installer's `.env`; use approved immutable digests for infrastructure
images as well. Copy the signed manifest into the client install directory as
`client-release-manifest.json`. Keep generated release artifacts and key
material out of source control. This host has not run this Docker release flow.

By default, the manifest allows a fresh database or a database already at this
release's Alembic head. After testing an upgrade from a specific older revision,
add `--approved-upgrade-from <revision>` to the release command; repeat the
option for each tested origin. The builder rejects revisions outside the release
migration history before starting the image builds. Migration ancestry alone is
not evidence that a customer upgrade was tested. The disposable lifecycle run
above passed only for its named source candidate; it does not validate this
worktree's later packaging changes. No production customer release or upgrade
is approved yet.

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
  --release-private-key /secure/owner-keys/release-private.key \
  --output /secure/releases/customer-installer.tar.gz
```

Run this owner-side command from the repository root. It verifies the release
signature, signed schema metadata and matching API/UI registry digests before
creating an archive. It refuses an existing output path and any unexpected
image-input keys, including secrets. It signs the exact deterministic archive
bytes with the same owner Ed25519 release key that signed the manifest and
creates `customer-installer.tar.gz.sig` beside the archive. It refuses a
private/public key mismatch and refuses to overwrite either output. The fixed
delivery set contains a customer installation guide, Compose/Caddy/preflight
files, the update runner and systemd units, a pinned `.env.example`, the signed
manifest, a convenience copy of the customer-side verifier, the public release
key and file checksums. No
application checkout, owner build/signing tools, local `.env` or private keys
are included. The verifier copy inside the archive cannot authenticate the
archive before extraction; obtain a trusted copy independently.

Deliver the installation ID and license token separately. Send the archive,
detached `.sig`, verifier CLI and trusted release public key through an
authenticated delivery channel. The recipient must obtain the verifier and
public key independently of the archive and verify the signature before
extracting or running archive contents. The public key inside the archive is
not a trust source for authenticating that archive. The file checksums inside
the archive detect accidental file changes. Packaging does not replace image
build, clean-install, owner-alert or upgrade/rollback acceptance.

### Sign an owner update envelope

After uploading the immutable installer archive to an HTTPS location reachable
by client installations, sign its release metadata offline. This command hashes
the exact archive bytes and creates the seven-field JSON envelope used by the
superadmin release screen. The release private key stays outside the repository
and is never uploaded:

```bash
python owner-tools/sign_client_update_release.py \
  --archive /secure/releases/customer-installer.tar.gz \
  --release-id client-1.48.0 \
  --version 1.48.0 \
  --archive-url https://releases.example.com/kodewaves/client-1.48.0.tar.gz \
  --min-current-version 1.47.0 \
  --notes "Security and reliability updates" \
  --release-private-key /secure/owner-keys/release-private.key \
  --trusted-public-key /secure/releases/release-public.key \
  --output /secure/releases/client-1.48.0.json
```

Paste the envelope fields into **Admin → Client Installations → Releases**,
review and publish it, then stage a rollout for active enrolled installation
IDs and activate it. The customer timer polls only the baked owner endpoint;
the API must verify both the owner-signed status and release signature before
it can download the archive. Keep the installer `.sig` sidecar for
authenticating initial customer downloads; the signed update envelope binds the
archive SHA-256 for automatic updates.

Pausing or stopping a rollout prevents new updates from starting. A client that
already reported `applying` may send its final signed applied, failed, or rolled
back result so the owner sees the actual outcome.

## Start and create the first administrator

Run commands from this directory so Compose resolves `.env` and the manifest
path consistently. Validate the inputs before Docker contacts any registry or
starts the services. Complete mandatory owner enrollment in `INSTALL.md` before
starting client services. Use `compose_client.py` for every Compose command; it
pins the project name and always includes the persistent recovery overlay. It
adds the identity overlay automatically after enrollment and shares an
OS-held operation lock with `recovery.py`, preventing Compose changes during
backup, restore, or rollback. Before every service-starting command, the wrapper
also reruns the local preflight and `docker compose config --quiet`; the explicit
checks below are useful for reviewing diagnostics before the first start:

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

When the optional `kodewaves-client-update.timer` is enabled, clients poll every
15 minutes and apply only a signed, published, targeted and activated owner
rollout. The updater downloads the immutable archive, verifies its owner-signed
digest and release manifest, checks schema compatibility, creates a cold
Postgres/MinIO backup, then updates only API/UI digest pins and the signed
manifest path. It rechecks rollout state immediately before activation and
reports signed per-installation progress. API/UI health and the database
migration head must match the signed release before it reports success; on
failure it restores the saved data volumes and release. Use
`python3 update_agent.py --directory /opt/kodewaves/client --check` to check
owner status without downloading or applying an update.

An application rollout changes the API/UI image pins and signed release
manifest. It verifies the other installer files in the downloaded archive but
does not replace the privileged updater, recovery helpers or host systemd
units. Updating those host-side control tools requires a separately reviewed
maintenance procedure; automatic updater self-replacement is not part of this
release path.

Keep the previous image digests, manifest and encrypted backup available for
recovery. By default, Docker restore
requires the active `.env` and manifest to match the archive. To restore an
older signed API/UI release as well as its data, explicitly pass
`--allow-release-rollback` and `--release-public-key`; the active signed release
must authorize the archived schema head in its `rollback_to` list. Only the
signed image references and manifest path change; installation credentials and
runtime settings must still match. The tool attempts to reinstate the candidate
release configuration and volumes if the prior release fails to start. This
compensating behavior has mocked tests but is not crash-atomic and has not been
accepted against a Docker daemon. For license renewal, follow `INSTALL.md` to
replace the token and recreate both the API and UI before the handover window
ends. A Compose restart does not reload changed environment variables. Follow
the license guide for key rotation, DNS changes and owner outage behavior.

The bundle's `recovery.py backup-docker` command can stop the project, verify no
running container still writes the Postgres or MinIO volumes, and create a cold
archive. `recovery.py restore --docker-volumes` stages data into new labeled
volumes and keeps the original set available for rollback with
`recovery.py rollback-docker`. When using `--allow-release-rollback`, that
command also restores the candidate image pins and manifest; pass the same
trusted `--release-public-key` used during restore. These Docker operations
have deterministic mocked failure-path tests but have not been exercised
against a Docker daemon; they are not yet accepted restore evidence. See
`INSTALL.md` for the required maintenance commands and limitations. Use
`compose_client.py` for every Compose operation so the project name and active
recovery volume mapping remain consistent. Owner enrollment is required before
starting services.

Do not roll back only the API/UI image pins after a release has saved model
provider credentials in the `fernet:v1` encrypted format. Earlier API images do
not decrypt that format. Use the cold pre-upgrade backup with
`recovery.py restore --docker-volumes --allow-release-rollback` to restore the
matching database volumes and signed prior images together. This returns data
to the backup point, so changes made after that backup are not retained. Treat
image-only rollback as unsupported.

Do not expose `.env`, the signed license token, database credentials or the
release manifest through a public web server. A customer with root control of
the host can alter local software and disable local monitoring; the signed
manifest is detection and enforcement within the unmodified client package,
not unbypassable remote attestation.
