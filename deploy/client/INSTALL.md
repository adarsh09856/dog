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
   `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`.
   Generate each other password or signing-secret placeholder independently.
5. The bundled Caddy proxy is enabled by `COMPOSE_PROFILES=direct-ingress` and
   obtains HTTPS certificates. Keep `CLIENT_CADDY_IPV4` and
   `FORWARDED_ALLOW_IPS` aligned. If an existing proxy handles HTTPS, clear
   `COMPOSE_PROFILES`, set `FORWARDED_ALLOW_IPS` to its actual peer IP/CIDR,
   and preserve the public Host header and original paths when routing
   `/api/v1` to `127.0.0.1:8000`, `/voice-audio` to `127.0.0.1:9000`, and
   other web requests to `127.0.0.1:3010`. Pass WebSocket upgrades through
   the API route. Expose TURN media directly; HTTP proxies do not carry it.

Do not put private credentials in the image-reference file or publish this
directory through a web server. Do not change or replace an approved image or
manifest independently. A changed API or UI file causes integrity enforcement
to deny access and report the finding when the owner service is reachable.

### Enrolled installation identity

Key enrollment requires an owner-issued enrollment token and matching approved
images. Complete enrollment with the owner before enabling the identity overlay;
enrolling a key without configuring the overlay will make owner checks fail.
Keep the enrolled 32-byte private key outside this installation directory and
back it up securely. Losing or replacing it requires owner-assisted recovery.

Set `CLIENT_IDENTITY_KEY_FILE` in `.env` to the absolute path of that existing
key and `CLIENT_IDENTITY_GID` to its nonzero numeric group. On a standard Linux
host, the file must be group-readable by that group and inaccessible to other
users, for example mode `0640`. Both API and UI containers join that group and
mount the key read-only. `python3 validate_install.py` checks the file and group.
After enrollment, add `-f docker-compose.identity.yaml` after
`-f docker-compose.client.yaml` to **every** Compose command below, including
the administrator bootstrap and future updates. For example:

```bash
docker compose -f docker-compose.client.yaml -f docker-compose.identity.yaml config --quiet
docker compose -f docker-compose.client.yaml -f docker-compose.identity.yaml up -d api
```

The enrollment tooling and live recovery process are still being validated;
do not use this overlay for production until your release passes acceptance.

## Start and create the administrator

Run these commands from the extracted installation directory:

```bash
python3 validate_install.py
docker compose -f docker-compose.client.yaml config --quiet
docker compose -f docker-compose.client.yaml pull
docker compose -f docker-compose.client.yaml up -d api
docker compose -f docker-compose.client.yaml ps
docker compose -f docker-compose.client.yaml logs --tail=100 api
```

Wait for API health and `Initial owner installation check succeeded` in its
logs. For a new empty installation, create the first local administrator:

```bash
docker compose -f docker-compose.client.yaml run --rm --no-deps api \
  python -m api.services.bootstrap_client_admin --email admin@customer.example.com
docker compose -f docker-compose.client.yaml up -d
```

The bootstrap command prompts for a password. It refuses to run after any user
or workspace exists. Sign in on your licensed HTTPS hostname. Client
administrators manage local users, workspaces and permitted branding in
Settings. The owner controls licenses, enabled features, limits and releases.
Public self-registration is disabled on client installations.

## Renewal and recovery

Keep encrypted backups of the database, persistent volumes and configuration.
For an update, use the supplied matching API/UI digests and signed manifest,
back up first, then recreate the services with Docker Compose. Rollback requires
explicit application/database compatibility approval; an old image alone is
insufficient. Install a replacement license before its handover window expires
and recreate the API service. Ask your installation owner for license,
domain/IP policy, renewal, capacity and recovery changes.

A host administrator can replace local software and disable local monitoring.
Integrity enforcement protects the approved, unmodified package; it is not
unbypassable attestation of a customer-controlled server.
