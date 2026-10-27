#!/usr/bin/env python3
"""Build both client-edition images and verify the owner route boundary."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from verify_images import verify_api, verify_caddyfile, verify_ui

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api.services.release_schema import migration_compatibility


def read_public_key(path: Path) -> str:
    value = path.read_text(encoding="ascii").strip()
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}=?", value):
            raise ValueError("non-canonical URL-safe Base64")
        raw_key = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True,
        )
        if base64.urlsafe_b64encode(raw_key).rstrip(b"=").decode("ascii") != value.rstrip("="):
            raise ValueError("non-canonical URL-safe Base64")
        Ed25519PublicKey.from_public_bytes(
            raw_key
        )
    except (TypeError, ValueError, binascii.Error) as exc:
        raise ValueError(f"Invalid Ed25519 public key file: {path}") from exc
    return value


def _repository_name(image_reference: str) -> str:
    """Remove a tag or digest from an image reference, preserving registry ports."""
    if "@" in image_reference:
        return image_reference.rsplit("@", 1)[0]
    slash = image_reference.rfind("/")
    colon = image_reference.rfind(":")
    return image_reference[:colon] if colon > slash else image_reference


def _pushed_digest(image_reference: str, repo_digests_json: str) -> str:
    repository = _repository_name(image_reference)
    first_component = repository.split("/", 1)[0]
    repositories = {repository}
    if "." not in first_component and ":" not in first_component and first_component != "localhost":
        repositories.add(f"docker.io/{repository}")
    repo_digests = json.loads(repo_digests_json)
    if not isinstance(repo_digests, list):
        raise TypeError(f"Docker returned no repository digests for {image_reference}")
    for value in repo_digests:
        if (
            isinstance(value, str)
            and any(value.startswith(f"{name}@sha256:") for name in repositories)
            and re.fullmatch(r"[^@]+@sha256:[0-9a-f]{64}", value)
        ):
            return value
    raise ValueError(f"No immutable repository digest found for {image_reference}")


def push_and_write_digest_env(
    api_tag: str, ui_tag: str, output: Path
) -> tuple[str, str]:
    """Push verified tags and write their immutable references for Compose."""
    pinned: list[str] = []
    for tag in (api_tag, ui_tag):
        repository = _repository_name(tag)
        if "/" not in repository:
            raise ValueError(
                f"Publish tags must include a registry or namespace: {tag}"
            )
        subprocess.run(["docker", "push", tag], check=True)
        inspected = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", tag],
            check=True,
            capture_output=True,
            text=True,
        )
        pinned.append(_pushed_digest(tag, inspected.stdout.strip()))

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        f"CLIENT_API_IMAGE={pinned[0]}\nCLIENT_UI_IMAGE={pinned[1]}\n",
        encoding="utf-8",
    )
    return pinned[0], pinned[1]


def inspect_image_id(tag: str) -> str:
    inspected = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", tag],
        check=True, capture_output=True, text=True,
    )
    image_id = inspected.stdout.strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError(f"Docker returned an invalid image ID for {tag}")
    return image_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-tag", default="kodewaves-client-api:local")
    parser.add_argument("--ui-tag", default="kodewaves-client-ui:local")
    parser.add_argument("--caddy-image", required=True, help="Approved immutable Caddy image digest used by client ingress")
    parser.add_argument("--license-public-key-file", required=True, type=Path, help="Owner license verification key baked into the API image")
    parser.add_argument("--legacy-license-public-key-file", action="append", type=Path, default=[], help="Previous owner license key to trust during a staged key rotation; repeat as needed")
    parser.add_argument("--release-public-key-file", required=True, type=Path, help="Owner release verification key baked into the API image")
    parser.add_argument("--owner-status-url", required=True, help="Owner HTTPS status endpoint baked into the API image")
    parser.add_argument("--owner-private-key", type=Path, help="Owner-only release signing key file")
    parser.add_argument("--manifest-output", type=Path, help="Where to write the signed release manifest")
    parser.add_argument("--public-key-output", type=Path, help="Where to write its public verification key")
    parser.add_argument("--inventory-metrics-output", type=Path, help="Write protected API/UI file counts and inventory scan durations")
    parser.add_argument("--approved-upgrade-from", action="append", default=[], help="Tested Alembic revision permitted for upgrade; repeat for each verified origin")
    parser.add_argument("--push", action="store_true", help="Push verified images to their tagged registries")
    parser.add_argument("--release-env-output", type=Path, help="Write API/UI @sha256 references after pushing")
    args = parser.parse_args()
    if any((args.owner_private_key, args.manifest_output, args.public_key_output)) and not all(
        (args.owner_private_key, args.manifest_output, args.public_key_output)
    ):
        parser.error("--owner-private-key, --manifest-output and --public-key-output must be used together")
    if args.approved_upgrade_from and not args.owner_private_key:
        parser.error("--approved-upgrade-from requires a signed release manifest")
    if args.push != (args.release_env_output is not None):
        parser.error("--push and --release-env-output must be used together")
    if args.push:
        if not args.owner_private_key:
            parser.error("--push requires an owner-signed release manifest")
        for tag in (args.api_tag, args.ui_tag):
            if "/" not in _repository_name(tag):
                parser.error(f"Publish tags must include a registry or namespace: {tag}")
    root = Path(__file__).resolve().parents[2]
    schema_compatibility = (
        migration_compatibility(root / "api" / "alembic" / "versions", args.approved_upgrade_from)
        if args.owner_private_key else None
    )
    license_public_key = read_public_key(args.license_public_key_file)
    previous_license_keys = list(dict.fromkeys(read_public_key(path) for path in args.legacy_license_public_key_file))
    previous_license_keys = [key for key in previous_license_keys if key != license_public_key]
    release_public_key = read_public_key(args.release_public_key_file)
    status_url = urlsplit(args.owner_status_url)
    if (
        status_url.scheme != "https" or not status_url.hostname
        or status_url.username or status_url.password or status_url.fragment
        or any(ord(character) < 33 or character in {'"', "\\"} for character in args.owner_status_url)
    ):
        parser.error("--owner-status-url must be an HTTPS URL without credentials or fragment")
    for dockerfile, tag in (("api/Dockerfile", args.api_tag), ("ui/Dockerfile", args.ui_tag)):
        command = ["docker", "build", "--build-arg", "KODEWAVES_EDITION=client"]
        if dockerfile == "api/Dockerfile":
            command.extend([
                "--build-arg", f"KODEWAVES_LICENSE_PUBLIC_KEY={license_public_key}",
                "--build-arg", f"KODEWAVES_LICENSE_PREVIOUS_PUBLIC_KEYS={','.join(previous_license_keys)}",
                "--build-arg", f"KODEWAVES_RELEASE_PUBLIC_KEY={release_public_key}",
                "--build-arg", f"KODEWAVES_OWNER_STATUS_URL={args.owner_status_url}",
            ])
        else:
            command.extend([
                "--build-arg", f"KODEWAVES_RELEASE_PUBLIC_KEY={release_public_key}",
                "--build-arg", f"KODEWAVES_OWNER_STATUS_URL={args.owner_status_url}",
            ])
        subprocess.run(
            [*command, "-f", dockerfile, "-t", tag, "."],
            cwd=root,
            check=True,
        )
    verify_api(args.api_tag)
    verify_ui(args.ui_tag)
    verify_caddyfile(args.caddy_image, str(root / "deploy" / "client" / "Caddyfile"))
    image_refs = None
    if args.push:
        # Resolve the immutable refs before signing so they are covered by the
        # owner signature. The env file is written only after verification.
        pinned = []
        for tag in (args.api_tag, args.ui_tag):
            subprocess.run(["docker", "push", tag], check=True)
            inspected = subprocess.run(
                ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", tag],
                check=True, capture_output=True, text=True,
            )
            pinned.append(_pushed_digest(tag, inspected.stdout.strip()))
        image_refs = {name: {"kind": "registry_digest", "reference": ref}
                      for name, ref in zip(("api", "ui"), pinned)}
    elif args.owner_private_key:
        image_refs = {name: {"kind": "image_id", "reference": inspect_image_id(tag)}
                      for name, tag in zip(("api", "ui"), (args.api_tag, args.ui_tag))}

    if args.owner_private_key:
        manifest = args.manifest_output.resolve()
        public_key_file = args.public_key_output.resolve()
        api_inventory_started = time.perf_counter()
        inventory = subprocess.run(
            [
                "docker", "run", "--rm", "--network", "none", "--entrypoint", "python",
                args.api_tag, "-c",
                "import json; from pathlib import Path; from api.services.release_integrity import protected_files; print(json.dumps(protected_files(Path('/app'))))",
            ],
            check=True, capture_output=True, text=True,
        )
        api_inventory_elapsed_ms = round((time.perf_counter() - api_inventory_started) * 1000, 1)
        api_files = json.loads(inventory.stdout)
        if not isinstance(api_files, dict):
            raise ValueError("API protected-file inventory must be a JSON object")
        ui_inventory_started = time.perf_counter()
        ui_inventory = subprocess.run(
            ["docker", "run", "--rm", "--network", "none", "--entrypoint", "node",
             args.ui_tag, "/app/verify-client-release.mjs", "--inventory"],
            check=True, capture_output=True, text=True,
        )
        ui_inventory_elapsed_ms = round((time.perf_counter() - ui_inventory_started) * 1000, 1)
        ui_files = json.loads(ui_inventory.stdout)
        if not isinstance(ui_files, dict):
            raise ValueError("UI protected-file inventory must be a JSON object")
        inventory_metrics = {
            "api": {"file_count": len(api_files), "elapsed_ms": api_inventory_elapsed_ms},
            "ui": {"file_count": len(ui_files), "elapsed_ms": ui_inventory_elapsed_ms},
        }
        if args.inventory_metrics_output:
            metrics_path = args.inventory_metrics_output.resolve()
            metrics_path.parent.mkdir(parents=True, exist_ok=True)
            metrics_path.write_text(json.dumps(inventory_metrics, indent=2) + "\n", encoding="utf-8")
        print(
            "Protected inventory scan: "
            f"API {len(api_files)} files/{api_inventory_elapsed_ms:.1f}ms; "
            f"UI {len(ui_files)} files/{ui_inventory_elapsed_ms:.1f}ms"
        )
        with tempfile.TemporaryDirectory() as directory:
            files_json = Path(directory) / "protected-files.json"
            ui_files_json = Path(directory) / "protected-ui-files.json"
            images_json = Path(directory) / "images.json"
            schema_json = Path(directory) / "schema-compatibility.json"
            files_json.write_text(json.dumps(api_files), encoding="utf-8")
            ui_files_json.write_text(json.dumps(ui_files), encoding="utf-8")
            images_json.write_text(json.dumps(image_refs), encoding="utf-8")
            schema_json.write_text(json.dumps(schema_compatibility), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable, str(root / "owner-tools" / "sign_client_release.py"),
                    "--files-json", str(files_json), "--private-key", str(args.owner_private_key.resolve()),
                    "--ui-files-json", str(ui_files_json),
                    "--images-json", str(images_json),
                    "--schema-compatibility-json", str(schema_json),
                    "--output", str(manifest), "--public-key-output", str(public_key_file),
                ],
                cwd=root,
                check=True,
            )
        if public_key_file.read_text(encoding="ascii").strip() != release_public_key:
            raise ValueError("Release signer does not match the verification key baked into the API image")
        subprocess.run(
            [
                "docker", "run", "--rm", "--network", "none",
                "--mount", f"type=bind,source={manifest},target=/app/client-release-manifest.json,readonly",
                "-e", "KODEWAVES_EDITION=client",
                "-e", "KODEWAVES_RELEASE_MANIFEST=/app/client-release-manifest.json",
                "-e", f"KODEWAVES_API_IMAGE={image_refs['api']['reference']}",
                "-e", f"KODEWAVES_UI_IMAGE={image_refs['ui']['reference']}",
                "--entrypoint", "python", args.api_tag, "-m", "api.services.release_integrity",
            ],
            check=True,
        )
        subprocess.run(
            [
                "docker", "run", "--rm", "--network", "none",
                "--mount", f"type=bind,source={manifest},target=/app/client-release-manifest.json,readonly",
                "-e", "KODEWAVES_EDITION=client",
                "-e", "KODEWAVES_RELEASE_MANIFEST=/app/client-release-manifest.json",
                "-e", f"KODEWAVES_API_IMAGE={image_refs['api']['reference']}",
                "-e", f"KODEWAVES_UI_IMAGE={image_refs['ui']['reference']}",
                "--entrypoint", "node", args.ui_tag, "/app/verify-client-release.mjs",
            ],
            check=True,
        )
        print("Signed release manifest matched the built API and UI images")
    if args.push:
        api_digest, ui_digest = image_refs["api"]["reference"], image_refs["ui"]["reference"]
        output = args.release_env_output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"CLIENT_API_IMAGE={api_digest}\nCLIENT_UI_IMAGE={ui_digest}\n", encoding="utf-8")
        print(f"Published API image: {api_digest}")
        print(f"Published UI image: {ui_digest}")
        print(f"Compose image references written to {args.release_env_output.resolve()}")
    print("Both client images built and owner source/routes were excluded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
