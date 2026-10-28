#!/usr/bin/env python3
"""Verify client images with disposable trust keys; never publish a release."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import yaml

from validate_install import validate as validate_client_install


def _temporary_keypair(directory: Path, name: str) -> tuple[Path, Path]:
    key = Ed25519PrivateKey.generate()
    private = directory / f"{name}-private.key"
    public = directory / f"{name}-public.key"
    private.write_bytes(key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    ))
    private.chmod(0o600)
    public.write_text(base64.urlsafe_b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode("ascii"), encoding="ascii")
    return private, public


def _read_inventory_metrics(path: Path) -> dict[str, dict[str, int | float]]:
    """Read bounded file-count and scan-time evidence from image verification."""
    metrics = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(metrics, dict) or set(metrics) != {"api", "ui"}:
        raise ValueError("Client image verification did not report both protected inventories")
    checked: dict[str, dict[str, int | float]] = {}
    for component, values in metrics.items():
        if not isinstance(values, dict) or set(values) != {"file_count", "elapsed_ms"}:
            raise ValueError(f"Invalid protected inventory metrics for {component}")
        count = values["file_count"]
        elapsed = values["elapsed_ms"]
        if (
            type(count) is not int or count < 1
            or isinstance(elapsed, bool) or not isinstance(elapsed, (int, float))
            or not math.isfinite(elapsed) or elapsed < 0
        ):
            raise ValueError(f"Invalid protected inventory metrics for {component}")
        checked[component] = {"file_count": count, "elapsed_ms": elapsed}
    return checked


def _verify_manifest_evidence(
    path: Path,
    inventory_metrics: dict[str, dict[str, int | float]],
    image_ids: dict[str, str],
) -> None:
    """Ensure CI evidence describes the signed inventories and exact built images."""
    signed = json.loads(path.read_text(encoding="utf-8"))
    payload = signed.get("payload") if isinstance(signed, dict) else None
    if not isinstance(payload, dict) or payload.get("edition") != "client":
        raise ValueError("Signed release manifest is missing its client payload")
    for component, key in (("api", "files"), ("ui", "ui_files")):
        inventory = payload.get(key)
        if not isinstance(inventory, dict) or len(inventory) != inventory_metrics[component]["file_count"]:
            raise ValueError(f"{component.upper()} inventory metrics do not match the signed manifest")
        image = payload.get("images", {}).get(component) if isinstance(payload.get("images"), dict) else None
        if (
            not isinstance(image, dict)
            or image.get("kind") != "image_id"
            or image.get("reference") != image_ids.get(component)
        ):
            raise ValueError(f"Signed {component.upper()} image ID does not match the inspected image")


def _verify_installer_config(root: Path, directory: Path, caddy_image: str) -> None:
    """Run the real installer preflight and Compose interpolation with disposable values."""
    credential_key = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode("ascii")
    values = {
        "CLIENT_API_IMAGE": "registry.example.com/kodewaves/client-api@sha256:" + "a" * 64,
        "CLIENT_UI_IMAGE": "registry.example.com/kodewaves/client-ui@sha256:" + "b" * 64,
        "CLIENT_POSTGRES_IMAGE": "registry.example.com/kodewaves/postgres@sha256:" + "c" * 64,
        "CLIENT_REDIS_IMAGE": "registry.example.com/kodewaves/redis@sha256:" + "d" * 64,
        "CLIENT_MINIO_IMAGE": "registry.example.com/kodewaves/minio@sha256:" + "e" * 64,
        "CLIENT_COTURN_IMAGE": "registry.example.com/kodewaves/coturn@sha256:" + "f" * 64,
        "CLIENT_CADDY_IMAGE": caddy_image,
        "COMPOSE_PROFILES": "direct-ingress",
        "KODEWAVES_INSTALLATION_ID": "ci-installation-123",
        "KODEWAVES_LICENSE_TOKEN": "ci-payload.ci-signature",
        "PUBLIC_HOST": "ci.customer.example.invalid",
        "TURN_HOST": "8.8.8.8",
        "POSTGRES_PASSWORD": "p" * 40,
        "REDIS_PASSWORD": "r" * 40,
        "MINIO_ROOT_USER": "kodewaves-ci-storage",
        "MINIO_ROOT_PASSWORD": "m" * 40,
        "OSS_JWT_SECRET": "j" * 40,
        "MASTER_CREDENTIAL_ENCRYPTION_KEY": credential_key,
        "TELEPHONY_WS_TOKEN_SECRET": "w" * 40,
        "TURN_SECRET": "t" * 40,
    }
    # The build's signed manifest deliberately uses local image IDs, which are
    # not distributable registry digests. Use a separate, explicitly unsigned
    # configuration fixture for Compose interpolation; never rewrite the signed
    # build evidence or claim these example registry images were installed.
    config_manifest = directory / "installer-config-only.json"
    config_manifest.write_text(json.dumps({
        "ci_configuration_fixture": True,
        "payload": {"images": {
            name: {"kind": "registry_digest", "reference": values[variable]}
            for name, variable in (("api", "CLIENT_API_IMAGE"), ("ui", "CLIENT_UI_IMAGE"))
        }},
    }), encoding="utf-8")
    values["CLIENT_RELEASE_MANIFEST_FILE"] = str(config_manifest.resolve())
    env_file = directory / "client-install-ci.env"
    env_file.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    compose_file = root / "deploy/client/docker-compose.client.yaml"
    preflight = validate_client_install(env_file, compose_file)
    failures = [message for message in preflight if not message.startswith("preflight passed;")]
    if failures:
        raise ValueError("Client installer preflight failed: " + "; ".join(failures))
    subprocess.run(
        ["docker", "compose", "--env-file", str(env_file), "-f", str(compose_file), "config", "--quiet"],
        cwd=root, check=True,
    )

    # Exercise the real nested interpolation, not just YAML syntax: changing
    # the bundled proxy address must also change the API's default trusted peer.
    values.update(
        CLIENT_INTERNAL_SUBNET="172.31.40.0/24",
        CLIENT_CADDY_IPV4="172.31.40.2",
    )
    custom_env = directory / "client-custom-network-ci.env"
    custom_env.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    custom_preflight = validate_client_install(custom_env, compose_file)
    failures = [message for message in custom_preflight if not message.startswith("preflight passed;")]
    if failures:
        raise ValueError("Custom-network installer preflight failed: " + "; ".join(failures))
    rendered = subprocess.run(
        ["docker", "compose", "--env-file", str(custom_env), "-f", str(compose_file), "config", "--format", "json"],
        cwd=root, check=True, capture_output=True, text=True,
    )
    services = json.loads(rendered.stdout)["services"]
    proxy_ip = services["caddy"]["networks"]["internal"]["ipv4_address"]
    trusted_peer = services["api"]["environment"]["FORWARDED_ALLOW_IPS"]
    if proxy_ip != values["CLIENT_CADDY_IPV4"] or trusted_peer != proxy_ip:
        raise ValueError("Rendered API proxy trust does not match the custom Caddy address")

    # Verify the enrolled-identity overlay too. The disposable key stays in the
    # temp directory outside the image build context and is never copied into
    # an image or release manifest.
    identity_key = directory / "ci-installation.key"
    identity_key.write_bytes(b"i" * 32)
    identity_key.chmod(0o640)
    identity_gid = getattr(os, "getegid", lambda: 12345)()
    if not 1 <= identity_gid <= 2**31 - 1:
        raise ValueError("Identity overlay verification requires a non-root group ID")
    identity_env_values = {
        **values,
        "CLIENT_IDENTITY_KEY_FILE": str(identity_key.resolve()),
        "CLIENT_IDENTITY_GID": str(identity_gid),
    }
    identity_env = directory / "client-identity-ci.env"
    identity_env.write_text(
        "".join(f"{key}={value}\n" for key, value in identity_env_values.items()),
        encoding="utf-8",
    )
    identity_preflight = validate_client_install(identity_env, compose_file)
    failures = [message for message in identity_preflight if not message.startswith("preflight passed;")]
    if failures:
        raise ValueError("Identity installer preflight failed: " + "; ".join(failures))
    overlay_path = root / "deploy/client/docker-compose.identity.yaml"
    overlay_services = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))["services"]
    for name in ("api", "ui"):
        mounts = overlay_services[name].get("volumes", [])
        if not any(
            isinstance(mount, dict) and mount.get("target") == "/run/kodewaves-identity/installation.key"
            and mount.get("bind", {}).get("create_host_path") is False
            for mount in mounts
        ):
            raise ValueError(f"{name.upper()} identity overlay must explicitly disable host path creation")
    identity_rendered = subprocess.run(
        [
            "docker", "compose", "--env-file", str(identity_env),
            "-f", str(compose_file), "-f", str(root / "deploy/client/docker-compose.identity.yaml"),
            "config", "--format", "json",
        ],
        cwd=root, check=True, capture_output=True, text=True,
    )
    identity_services = json.loads(identity_rendered.stdout)["services"]
    for service_name in ("api", "ui"):
        service = identity_services[service_name]
        expected_mount = {
            "type": "bind",
            "source": str(identity_key.resolve()),
            "target": "/run/kodewaves-identity/installation.key",
            "read_only": True,
            "bind": {"create_host_path": False},
        }
        if service.get("group_add") != [str(identity_gid)]:
            raise ValueError(f"Rendered {service_name.upper()} identity group does not match the key group")
        mounts = [mount for mount in service.get("volumes", []) if mount.get("target") == expected_mount["target"]]
        if len(mounts) != 1 or any(
            mounts[0].get(field) != expected_mount[field] for field in ("type", "source", "target", "read_only")
        ) or mounts[0].get("bind") not in ({}, {"create_host_path": False}):
            mounts = [mount for mount in service.get("volumes", []) if mount.get("target") == expected_mount["target"]]
            raise ValueError(
                f"Rendered {service_name.upper()} identity key mount is not read-only and non-creating: "
                f"{json.dumps(mounts, sort_keys=True)}"
            )
        if service.get("environment", {}).get("KODEWAVES_INSTALLATION_KEY_FILE") != expected_mount["target"]:
            raise ValueError(f"Rendered {service_name.upper()} identity key path does not match its mount")


def verify(caddy_image: str, report: Path) -> None:
    if not re.fullmatch(r"[^@]+@sha256:[0-9a-f]{64}", caddy_image):
        raise ValueError("Caddy image must use an approved immutable sha256 digest")
    if report.exists():
        raise ValueError("Report already exists; use a new path for fresh verification")
    root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="kodewaves-ci-trust-") as temporary:
        directory = Path(temporary)
        if directory.resolve().is_relative_to(root):
            raise ValueError("Temporary signing keys must be outside the Docker build context")
        _, license_public = _temporary_keypair(directory, "license")
        release_private, release_public = _temporary_keypair(directory, "release")
        manifest = directory / "client-release-manifest.json"
        inventory_metrics_file = directory / "protected-inventory-metrics.json"
        api_image, ui_image = "kodewaves-client-api:ci-check", "kodewaves-client-ui:ci-check"
        subprocess.run([
            sys.executable, str(root / "deploy/client/build_and_verify.py"),
            "--api-tag", api_image, "--ui-tag", ui_image,
            "--caddy-image", caddy_image,
            "--license-public-key-file", str(license_public),
            "--release-public-key-file", str(release_public),
            "--owner-status-url", "https://owner-ci.invalid/api/v1/admin/client-installations/check",
            "--owner-private-key", str(release_private),
            "--manifest-output", str(manifest),
            "--public-key-output", str(directory / "signed-release-public.key"),
            "--inventory-metrics-output", str(inventory_metrics_file),
        ], cwd=root, check=True)
        inventory_metrics = _read_inventory_metrics(inventory_metrics_file)
        _verify_installer_config(root, directory, caddy_image)
        image_ids = {}
        for name, image in (("api", api_image), ("ui", ui_image)):
            inspected = subprocess.run(
                ["docker", "image", "inspect", "--format", "{{.Id}}", image],
                check=True, capture_output=True, text=True,
            )
            image_id = inspected.stdout.strip()
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
                raise ValueError(f"Missing immutable {name} image ID")
            image_ids[name] = image_id
        _verify_manifest_evidence(manifest, inventory_metrics, image_ids)
        evidence = {
            "status": "passed", "production_release": False,
            "scope": "Client image boundaries, Caddy syntax, signed API/UI inventories, installer preflight, Compose interpolation and enrolled identity overlay",
            "installer_preflight": "passed", "compose_config": "passed",
            "installer_manifest_scope": "Unsigned configuration fixture; signed build inventories and image IDs verified separately",
            "custom_network_proxy_config": "passed",
            "identity_overlay_config": "passed",
            "startup_tamper_rejection": "passed",
            "protected_inventory": inventory_metrics,
            "not_verified": ["clean install", "upgrade/rollback", "live owner alerts", "browser audio", "telephone"],
            "image_ids": image_ids, "caddy_image": caddy_image,
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        }
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caddy-image", required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    verify(args.caddy_image, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
