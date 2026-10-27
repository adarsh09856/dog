#!/usr/bin/env python3
"""Inspect built client images before distributing them to a customer."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys


def _run(*args: str) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def verify_api(image: str) -> None:
    code = """
import os
from pathlib import Path
from api.services.deployment_edition import IMAGE_EDITION

root = Path('/app')
assert os.environ.get('KODEWAVES_EDITION') == 'client', 'API image is not client edition'
assert IMAGE_EDITION == 'client', 'API image edition is not pinned to client'
assert os.getuid() != 0, 'API image must run as a non-root user'
assert os.getuid() == 10001, 'API runtime UID must match the client cache volume owner'
for path in ('api/routes/admin', 'api/routes/superuser.py', 'api/tests',
             'api/db/owner_user_management.py', 'api/db/saas_plan_catalog.py',
             'scripts/create_superuser.py'):
    assert not (root / path).exists(), f'Owner/test source shipped: {path}'
for path in ('api/services/installation_license.py', 'api/services/release_integrity.py',
             'api/services/release_schema.py',
             'api/services/owner_public_keys.json',
             'api/services/bootstrap_client_admin.py',
             'api/db/client_user_management.py', 'api/db/client_workspace_management.py',
             'scripts/start_services_docker.sh', 'scripts/run_web.sh',
             'docs/docs.json'):
    assert (root / path).is_file(), f'Client runtime file missing: {path}'
for path in ('owner-tools', 'api/.env', 'api/.env.test'):
    assert not (root / path).exists(), f'Owner or local secret source shipped: {path}'
import json
trust = json.loads((root / 'api/services/owner_public_keys.json').read_text())
assert trust.get('license') and trust.get('release') and trust.get('owner_status_url'), 'Owner trust settings are missing'
from api.services.release_schema import verify_client_schema_before_migration
assert callable(verify_client_schema_before_migration), 'Client schema preflight is unavailable'
from api.app import app
paths = set(app.openapi()['paths'])
owner = [path for path in paths if path == '/admin' or path.startswith('/admin/')
         or path == '/superuser' or path.startswith('/superuser/')
         or path == '/api/v1/admin' or path.startswith('/api/v1/admin/')
         or path == '/api/v1/superuser' or path.startswith('/api/v1/superuser/')]
assert not owner, f'Owner-only API routes shipped: {owner}'
assert '/api/v1/installation/license' in paths, 'Client license status route is missing'
print(f'Client API source and route boundary verified ({len(paths)} routes)')
"""
    print(_run(
        "docker", "run", "--rm", "--network", "none",
        "-e", "ENVIRONMENT=test",
        "-e", "DEPLOYMENT_MODE=oss",
        "-e", "DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1:5432/test",
        "-e", "REDIS_URL=redis://127.0.0.1:6379/0",
        "--entrypoint", "python", image, "-c", code,
    ))


def verify_ui(image: str) -> None:
    code = """
const fs = require('fs');
if (process.env.KODEWAVES_EDITION !== 'client') {
  throw new Error('UI image is not pinned to client edition');
}
if (typeof process.getuid === 'function' && process.getuid() === 0) {
  throw new Error('Client UI image must run as a non-root user');
}
const path = '/app/.next/server/app-paths-manifest.json';
for (const required of ['/app/verify-client-release.mjs', '/app/client-release-public-key', '/app/client-owner-status-url']) {
  if (!fs.existsSync(required)) throw new Error(`Client UI integrity runtime file missing: ${required}`);
}
const routes = Object.keys(JSON.parse(fs.readFileSync(path, 'utf8')));
const owner = routes.filter(route => route === '/admin/page' || route.startsWith('/admin/')
  || route === '/superadmin/page' || route.startsWith('/superadmin/'));
const privileged = routes.filter(route => route === '/impersonate/route' || route.startsWith('/impersonate/'));
if (owner.length || privileged.length) {
  throw new Error(`Owner-only UI routes shipped: ${[...owner, ...privileged].join(', ')}`);
}
if (!routes.includes('/page')) throw new Error('Public page missing from client UI');
const routing = JSON.parse(fs.readFileSync('/app/.next/routes-manifest.json', 'utf8'));
const rewrites = routing.rewrites || {};
const deployedRewrites = Array.isArray(rewrites)
  ? rewrites
  : Object.values(rewrites).flat();
if (deployedRewrites.length) {
  throw new Error(`Client UI image contains unexpected proxy rewrites: ${deployedRewrites.map(route => route.source).join(', ')}`);
}
console.log(`Client UI route boundary verified (${routes.length} routes)`);
"""
    print(_run("docker", "run", "--rm", "--network", "none", "--entrypoint", "node", image, "-e", code))


def verify_caddyfile(image: str, caddyfile: str) -> None:
    """Validate ingress syntax with the same immutable Caddy image clients run."""
    if not re.fullmatch(r"[^@]+@sha256:[0-9a-f]{64}", image):
        raise ValueError("Caddy image must be pinned to an immutable sha256 digest")
    print(_run(
        "docker", "run", "--rm", "--network", "none",
        "-e", "PUBLIC_HOST=validation.invalid",
        "--mount", f"type=bind,source={caddyfile},target=/etc/caddy/Caddyfile,readonly",
        "--entrypoint", "caddy", image,
        "validate", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile",
    ))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-image", required=True)
    parser.add_argument("--ui-image", required=True)
    args = parser.parse_args()
    try:
        verify_api(args.api_image)
        verify_ui(args.ui_image)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        print(f"Client image verification failed: {detail}", file=sys.stderr)
        return 1
    print(json.dumps({"api_image": args.api_image, "ui_image": args.ui_image, "verified": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
