#!/usr/bin/env python3
"""Inspect built client images before distributing them to a customer."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def _run(*args: str) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def verify_api(image: str, *, allow_legacy_owner_persistence: bool = False) -> None:
    # A prior client release may still contain this unused owner-side DB helper.
    # Permit that one legacy path only when validating the source being upgraded
    # from; candidate releases must continue to omit it.
    code = """
import os
import ctypes
import subprocess
from pathlib import Path
from api.services.deployment_edition import IMAGE_EDITION

root = Path('/app')
allow_legacy_owner_persistence = __LEGACY_OWNER_PERSISTENCE_ALLOWED__
assert os.environ.get('KODEWAVES_EDITION') == 'client', 'API image is not client edition'
assert IMAGE_EDITION == 'client', 'API image edition is not pinned to client'
assert os.getuid() != 0, 'API image must run as a non-root user'
assert os.getuid() == 10001, 'API runtime UID must match the client cache volume owner'
rnnoise = root / 'api/native/rnnoise/librnnoise.so'
assert rnnoise.is_file() and not rnnoise.is_symlink(), 'Client RNNoise library must be a regular file'
ctypes.CDLL(str(rnnoise))
subprocess.run(['node', '-e', "require('/app/api/mcp_server/ts_validator/node_modules/typescript')"], check=True)
for path in ('api/routes/admin', 'api/routes/superuser.py', 'api/tests',
             'api/db/owner_user_management.py', 'api/db/saas_plan_catalog.py',
             'api/db/client_installations.py',
             'api/services/owner_license_signer.py',
             'api/services/owner_license_signer_client.py',
             'scripts/create_superuser.py'):
    if path == 'api/db/client_installations.py' and allow_legacy_owner_persistence:
        legacy_path = root / path
        assert not legacy_path.is_symlink(), 'Legacy installation persistence path must not be a symlink'
        continue
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
""".replace(
        "__LEGACY_OWNER_PERSISTENCE_ALLOWED__", repr(allow_legacy_owner_persistence),
    )
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


def verify_startup_rejection(api_image: str, ui_image: str, manifest: Path) -> None:
    """Require built verifiers to reject changed files and invalid signatures.

    Run only after both images accepted this exact manifest. No customer license,
    owner credentials, network, database or persistent volume is supplied.
    """
    with tempfile.TemporaryDirectory(prefix="kodewaves-image-tamper-") as temporary:
        directory = Path(temporary)
        changed = directory / "changed.json"
        changed.write_text("{}\n", encoding="utf-8")
        changed.chmod(0o644)
        invalid_signed = json.loads(manifest.read_text(encoding="utf-8"))
        image_metadata = invalid_signed["payload"]["images"]
        invalid_signed["signature"] = "A" * 86
        invalid_manifest = directory / "invalid-signature.json"
        invalid_manifest.write_text(json.dumps(invalid_signed), encoding="utf-8")
        invalid_manifest.chmod(0o644)
        for component, image, entrypoint, arguments, protected, file_error, signature_error in (
            ("api", api_image, "python", ["-m", "api.services.release_integrity"],
             "/app/docs/docs.json", "Protected client release files differ from the signed manifest",
             "Client release manifest is missing or invalid"),
            ("ui", ui_image, "node", ["/app/verify-client-release.mjs"],
             "/app/.next/server/app-paths-manifest.json",
             "Client UI integrity check failed: .next/server/app-paths-manifest.json",
             "Client release manifest signature is invalid"),
        ):
            for case in ("changed_file", "invalid_signature"):
                selected_manifest = manifest if case == "changed_file" else invalid_manifest
                command = [
                    "docker", "run", "--rm", "--network", "none", "--read-only",
                    "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
                    "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777",
                    "--mount", f"type=bind,source={selected_manifest.resolve()},target=/app/client-release-manifest.json,readonly",
                    "-e", "KODEWAVES_EDITION=client",
                    "-e", "KODEWAVES_RELEASE_MANIFEST=/app/client-release-manifest.json",
                    "-e", f"KODEWAVES_API_IMAGE={image_metadata['api']['reference']}",
                    "-e", f"KODEWAVES_UI_IMAGE={image_metadata['ui']['reference']}",
                ]
                if case == "changed_file":
                    command += ["--mount", f"type=bind,source={changed},target={protected},readonly"]
                command += ["--entrypoint", entrypoint, image, *arguments]
                result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
                expected = file_error if case == "changed_file" else signature_error
                detail = result.stdout + result.stderr
                if result.returncode != 1 or expected not in detail:
                    raise ValueError(
                        f"{component.upper()} {case} startup rejection was not proved "
                        f"(exit {result.returncode}): {detail[-4000:]}"
                    )
                print(f"Client {component.upper()} rejected {case} at startup")


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
