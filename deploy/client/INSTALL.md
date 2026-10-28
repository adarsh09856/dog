# Install your Kodewaves client edition

This package contains the installation configuration and an owner-signed release
manifest. Application images are downloaded from the approved registry when you
run Docker Compose. Your installation ID and license token are delivered
separately. Keep the token and server credentials private.

This package must pass installation acceptance with your approved release before
production use. Packaging a release does not certify its deployment or rollback.

## Prepare the server

Use a Linux server with Python 3, Docker Engine and the Docker Compose plugin.
Provide the server capacity and registry access agreed for your models and call
volume. Point the licensed hostname at this server. Allow TCP 80/443, UDP 443,
TURN UDP/TCP 3478 and UDP 49152-49200 through its firewall. Back up an existing
installation before changing images or credentials.

Extract this archive into a private installation directory. Check `SHA256SUMS`
against the package you received, and verify the archive checksum through your
trusted delivery channel. A checksum stored inside an archive does not
authenticate its sender. The release public key is also included for operator
inspection; the application images use their own baked verification keys.

## Configure this installation

1. Copy `.env.example` to `.env` and restrict it with `chmod 600 .env`.
2. Keep the supplied image digests and signed release manifest together. Set
   `CLIENT_RELEASE_MANIFEST_FILE=./client-release-manifest.json`.
3. Set `KODEWAVES_INSTALLATION_ID`, `KODEWAVES_LICENSE_TOKEN` and `PUBLIC_HOST`
   to the values assigned to this installation. Set `TURN_HOST` to the server's
   globally routable public IPv4 address. This installer does not configure IPv6 TURN.
4. Generate fresh credentials for every secret placeholder. The credential
   encryption key must contain 32 random bytes encoded as URL-safe Base64:
   `python3 -c 'import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'`.
   Generate each other password or signing-secret placeholder independently.
   Preserve the encryption key's exact text, including its trailing `=`, in
   backups and updates. For an existing installation, do not add or remove
   padding: the current API derives a different encryption key for unpadded
   input, and changing that text can make saved provider credentials unreadable.
5. The bundled Caddy proxy is enabled by `COMPOSE_PROFILES=direct-ingress` and
   obtains HTTPS certificates. Keep `CLIENT_CADDY_IPV4` and
   `FORWARDED_ALLOW_IPS` aligned. If an existing proxy handles HTTPS, clear
   `COMPOSE_PROFILES`, set `FORWARDED_ALLOW_IPS` to its actual peer IP/CIDR,
   and preserve the public Host header and original paths when routing
   `/api/v1` to `127.0.0.1:8000`, `/voice-audio` to `127.0.0.1:9000`, and
   other web requests to `127.0.0.1:3010`. Pass WebSocket upgrades through
   the API route. Expose TURN media directly; HTTP proxies do not carry it.
   If you change `API_PORT`, `UI_PORT` or `MINIO_PORT`, use those ports in
   your external proxy instead of the defaults. The three ports must differ.

Do not put private credentials in the image-reference file or publish this
directory through a web server. Do not change or replace an approved image or
manifest independently. A changed API or UI file causes integrity enforcement
to deny access and report the finding when the owner service is reachable.

### Enrolled installation identity

Owner enrollment is mandatory before starting or entering any client service.
Key enrollment requires an owner-issued enrollment token and matching approved
images. The bundled Compose wrapper refuses `up`, `start`, `restart`, `run`,
`exec`, `create` and `scale` until the identity key exists, and always selects
the recovery overlay so a restored installation cannot silently revert to old
volume names.
Keep the enrolled 32-byte private key outside this installation directory and
back it up securely. Losing or replacing it requires owner-assisted recovery.

Set `CLIENT_IDENTITY_KEY_FILE` in `.env` to an absolute path in an existing
private directory and `CLIENT_IDENTITY_GID` to a nonzero numeric group permitted
to read the key. Pull the approved API image first, then run the enrollment
command and enter the owner's one-time token at its prompt:

```bash
python3 compose_client.py pull api
python3 enroll_identity.py
```

The command creates the key once on this server, uses the approved API image's
baked owner endpoint and verification keys, and verifies the signed owner
response. It does not send the private key to the owner. On a standard Linux
host, the key must be group-readable by the configured group and inaccessible
to other users, for example mode `0640`. Both API and UI containers join that
group and mount the key read-only. `python3 validate_install.py` checks the file
and group. To verify a previously enrolled key without creating or replacing
it, run `python3 enroll_identity.py --verify-only`. Use `compose_client.py` for
all Compose operations; it selects the identity overlay automatically once the
configured key exists. Do not pass Compose file, project, or env-file override
options to it, because they could switch an existing installation to different
volumes or bypass the enrolled identity. The project name comes from
`COMPOSE_PROJECT_NAME` in `.env`, or the installation directory name when that
setting is absent. Preserve that value on upgrades and recovery.

```bash
python3 compose_client.py config --quiet
python3 compose_client.py up -d api
```

The enrollment tooling and live recovery process still require installation
acceptance; do not use this overlay for production until your release passes it.

## Start and create the administrator

Run these commands from the extracted installation directory:

```bash
python3 validate_install.py
python3 compose_client.py config --quiet
python3 compose_client.py pull
python3 compose_client.py up -d api
python3 compose_client.py ps
python3 compose_client.py logs --tail=100 api
```

Wait for API health and `Initial owner installation check succeeded` in its
logs. For a new empty installation, create the first local administrator:

```bash
python3 compose_client.py run --rm --no-deps api \
  python -m api.services.bootstrap_client_admin --email admin@customer.example.com
python3 compose_client.py up -d
```

The bootstrap command prompts for a password. It refuses to run after any user
or workspace exists. Sign in on your licensed HTTPS hostname. Client
administrators manage local users, workspaces and permitted branding in
Settings. The owner controls licenses, enabled features, limits and releases.
Public self-registration is disabled on client installations.

## Renewal and recovery

Keep encrypted backups of the database, persistent volumes and configuration.
Treat the database and object storage as one recovery set: the Compose stack
stores application records in `postgres_data` and uploaded objects/recordings
in `minio_data`. An unmatched restore can leave database references pointing
to missing objects. `redis_data` can contain queue and owner-check state; its
recovery must be planned with the owner to avoid replaying old work. Preserve
the `.env` secrets, signed manifest, exact image digests and the enrolled
identity key separately in encrypted, access-controlled backups. The identity
key must be restored with its original group and permissions; ask the owner
for recovery if it is unavailable.

Arrange a maintenance window, stop new calls and background writes, and use
the commands below to stop the complete Compose project before taking a cold
snapshot. The backup command also checks that no other running container still
mounts either data volume. It refuses missing volumes rather than allowing
Docker to create an empty replacement. Keep the source archive encrypted and
test restoration on an isolated host without live telephony or outbound jobs
before relying on it.

The customer bundle includes `recovery.py` for offline archive validation and
staging, plus controlled Compose volume export and restore. Create a cold backup
with:

```bash
python3 recovery.py backup-docker \
  --env-file .env \
  --release-public-key ./release-public-key.txt \
  --output /secure/backups/client-recovery.tar.gz \
  --confirm-maintenance
```

This stops all services in this Compose project, confirms Postgres and MinIO
volumes exist and have no running container consumers (including containers in
other projects), exports both volumes read-only, packages the exact
installation configuration and identity key, then restarts only the services
that were running before the backup. If restart fails, the archive may exist
and the command reports that services need operator recovery. The command uses
the approved pinned Postgres image as a tar helper and never pulls images.
Postgres tablespace symlinks are refused. Redis is intentionally not included;
it starts with a fresh queue after restore.

To restore, first validate and stage into new volumes; the existing volumes are
kept intact and available for rollback:

```bash
python3 recovery.py restore /secure/backups/client-recovery.tar.gz \
  --docker-volumes --env-file .env --confirm-maintenance
```

The restore accepts an archive only when installation ID, `.env`, signed
manifest and enrolled key match the current installation. It creates uniquely
labeled Postgres/MinIO/Redis volumes and selects them through the persistent
`docker-compose.recovery.yaml` override. It waits for the services that were
running before the maintenance window to become healthy. The old volumes and
new volumes are both retained. Roll back the selection with:

```bash
python3 recovery.py rollback-docker --env-file .env --confirm-maintenance
```

Do not remove either volume set until the restored application and its data
have been checked. If the process is interrupted, inspect
`.client-recovery-state/state.json`; the tool does not automatically delete
volumes whose selection is uncertain. The Docker path has not yet been
exercised against a live Docker daemon in CI or on an isolated installation, so
this package feature is not customer-accepted disaster-recovery proof.

The `recovery.py create` command remains available when an approved external
process produced cold volume tar files:

```bash
python3 recovery.py create \
  --postgres-tar /secure/staging/postgres.tar \
  --minio-tar /secure/staging/minio.tar \
  --env-file .env \
  --manifest ./client-release-manifest.json \
  --release-public-key ./release-public-key.txt \
  --identity-key /secure/identity/installation.key \
  --confirm-stopped-writers \
  --output /secure/backups/client-recovery.tar.gz
```

Omit `--identity-key` only when identity enrollment is not configured. The tool
refuses symlinks, non-tar volume exports, mismatched installation/image
identities, wrong identity-key group/mode, and existing output paths. Store the
result encrypted and access-controlled. Validate it later with:

```bash
python3 recovery.py validate /secure/backups/client-recovery.tar.gz
```

For an offline staging check, extract to a **new** directory:

```bash
python3 recovery.py restore /secure/backups/client-recovery.tar.gz \
  --destination /secure/staging/client-restore-check
```

Staging is non-destructive and never modifies live Docker volumes. It validates
checksums and paths, writes the preserved config and original volume archives,
and unpacks the volume contents into `volumes/postgres-data/` and
`volumes/minio-data/` inside the new directory. On Linux, use an operator
account with permission to preserve the archived file UID/GID (normally root).
The tool checks available disk space before extraction. Staging does not
initialize a Compose stack or prove that services can start from those files.
The maintenance flag is an operator attestation, not machine-verifiable proof
that writers stopped. Exports with
Postgres tablespace symlinks are refused and require an owner-approved backup
method. The archive contains installation secrets and customer data; protect it
accordingly. Docker-volume restoration and a full service recovery exercise
remain unverified. The archive checksums detect accidental damage; they do not
authenticate the archive against a malicious rewrite, so keep backups in a
trusted, access-controlled location and compare delivery hashes out of band.

For an update, use the supplied matching API/UI digests and signed manifest,
back up first, then recreate the services with Docker Compose. Before applying
Alembic migrations, API startup checks the current database revision against
the signed manifest's `schema_compatibility.upgrade_from` list. An unknown,
ambiguous, or unapproved revision stops startup before migrations run; resolve
the mismatch with the installation owner and restore a compatible backup when
needed. Rollback requires explicit application/database compatibility approval;
an old image alone is insufficient. For license renewal, replace
`KODEWAVES_LICENSE_TOKEN` in `.env` before the handover window expires, then
recreate both API and UI so they receive the new environment. A Compose
`restart` does not reload changed environment values:

```bash
python3 validate_install.py
python3 compose_client.py up -d --no-deps --force-recreate api
```

Wait for API health and `Initial owner installation check succeeded`, then run:

```bash
python3 compose_client.py up -d --no-deps --force-recreate ui
python3 compose_client.py ps
```

The UI also needs the new token to report integrity failures to the owner.
Use `compose_client.py` for later update, bootstrap and log operations so the
same project, identity and recovery volume selection stays active. Ask your
installation owner for license, domain/IP policy, renewal, capacity and
recovery changes.

If the bundled ingress displays “Service temporarily unavailable,” check the
API and UI container logs and contact the installation owner. This message can
also appear during ordinary outages; the logs and owner integrity alerts identify
whether a protected-file check failed. An external proxy needs its own equivalent
error response.

A host administrator can replace local software and disable local monitoring.
Integrity enforcement protects the approved, unmodified package; it is not
unbypassable attestation of a customer-controlled server.
