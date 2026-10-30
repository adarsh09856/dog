#!/usr/bin/env python3
"""Verify client images with disposable trust keys; never publish a release."""

from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import math
import os
import re
import secrets
import ssl
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml
from compose_client import controlled_environment
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from validate_install import PINNED_IMAGE
from validate_install import validate as validate_client_install

# Immutable upstream multi-arch manifests for pgvector/pgvector:pg17 and
# library/redis:7, used only by the disposable CI runtime smoke. The MinIO
# service image is built from this repository's version-pinned Dockerfile and
# removed after the smoke.
_CI_POSTGRES_IMAGE = (
    "docker.io/pgvector/pgvector@sha256:"
    "ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d"
)
_CI_REDIS_IMAGE = (
    "docker.io/library/redis@sha256:"
    "b6b6e3dc0c0952737748e55d5d885272840c7e42ba41ab1d5489f693419882f5"
)


class _OwnerAcceptanceServer:
    """Disposable HTTPS owner protocol peer for the packaged-client acceptance smoke."""

    def __init__(self, directory: Path, license_token: str, license_private: bytes, license_public: str):
        from api.services.installation_license import load_license

        self.license_token = license_token
        self.license_private = license_private
        self.license_public = license_public
        license_data = load_license(license_token, license_public)
        self.installation_id = license_data.installation_id
        self.license_fingerprint = hashlib.sha256(license_token.encode("ascii")).hexdigest()
        self.enrollment_token = secrets.token_urlsafe(40)
        self.public_key: str | None = None
        self.binding_valid = True
        self.used_nonces: set[str] = set()
        self._lock = threading.Lock()
        self.ca_file = directory / "ci-owner-ca.pem"
        self.server_key_file = directory / "ci-owner-server.key"
        self.server_cert_file = directory / "ci-owner-server.pem"
        self._make_certificates()

        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 1_048_576:
                        raise ValueError("invalid request size")
                    body = json.loads(self.rfile.read(length))
                    if self.headers.get("Authorization") != f"Bearer {owner.license_token}":
                        self._reply(401, {"detail": "Invalid installation token"})
                        return
                    if self.path.endswith("/enroll"):
                        result = owner.enroll(body)
                    elif self.path.endswith("/check"):
                        result = owner.check(body)
                    else:
                        self._reply(404, {"detail": "Not found"})
                        return
                    self._reply(200, result)
                except Exception:  # noqa: BLE001 - do not expose protocol secrets in test logs
                    self._reply(401, {"detail": "Invalid CI owner request"})

            def _reply(self, status: int, payload: dict) -> None:
                data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, _format, *_args):
                return

        self.httpd = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(str(self.server_cert_file), str(self.server_key_file))
        self.httpd.socket = tls.wrap_socket(self.httpd.socket, server_side=True)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.httpd.server_address[1]
        self.url = f"https://host.docker.internal:{self.port}/api/v1/admin/client-installations/check"

    def _make_certificates(self) -> None:
        now = datetime.now(UTC)
        ca_key = Ed25519PrivateKey.generate()
        ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Kodewaves disposable CI owner CA")])
        ca = (
            x509.CertificateBuilder()
            .subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=2))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.KeyUsage(
                digital_signature=False, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=None, decipher_only=None,
            ), critical=True)
            .sign(ca_key, algorithm=None)
        )
        leaf_key = Ed25519PrivateKey.generate()
        leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "host.docker.internal")])
        leaf = (
            x509.CertificateBuilder()
            .subject_name(leaf_name).issuer_name(ca.subject).public_key(leaf_key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName("host.docker.internal"), x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            ]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
            )
            .sign(ca_key, algorithm=None)
        )
        self.ca_file.write_bytes(ca.public_bytes(Encoding.PEM))
        self.server_key_file.write_bytes(leaf_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
        self.server_cert_file.write_bytes(leaf.public_bytes(Encoding.PEM))
        for path in (self.ca_file, self.server_key_file):
            path.chmod(0o600)

    def enroll(self, body: dict) -> dict:
        from api.services.installation_identity import verify_enrollment

        with self._lock:
            if self.public_key is not None or body.get("enrollment_token") != self.enrollment_token:
                raise ValueError("invalid one-time enrollment token")
            verify_enrollment(
                public_key=body["public_key"], signature=body["signature"],
                installation_id=self.installation_id, license_token=self.license_token,
                enrollment_token=self.enrollment_token, nonce=body["nonce"], issued_at=body["issued_at"],
            )
            self.public_key = body["public_key"]
        return {"enrolled": True}

    def check(self, body: dict) -> dict:
        from api.services.installation_identity import verify_owner_check
        from api.services.installation_license import issue_license_token

        with self._lock:
            if self.public_key is None:
                raise ValueError("installation is not enrolled")
            nonce = body["nonce"]
            if nonce in self.used_nonces:
                raise ValueError("owner-check nonce replay")
            verify_owner_check(
                self.public_key, body["proof_signature"],
                installation_id=self.installation_id, license_token=self.license_token,
                nonce=nonce, issued_at=body["proof_issued_at"],
                integrity_ok=body["integrity_ok"], integrity_finding=body["integrity_finding"],
            )
            self.used_nonces.add(nonce)
            binding_valid = self.binding_valid
        now = int(time.time())
        status = {
            "kind": "installation_status", "installation_id": self.installation_id,
            "license_sha256": self.license_fingerprint, "nonce": nonce,
            "revoked": False, "binding_valid": binding_valid, "observed_ip": "127.0.0.1",
            "issued_at": now, "expires_at": now + 300,
        }
        return {"signed_status": issue_license_token(status, self.license_private)}

    def set_binding_valid(self, binding_valid: bool) -> None:
        """Control the signed IP decision in the disposable acceptance peer."""
        with self._lock:
            self.binding_valid = binding_valid

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def normalize_caddy_image(image: str) -> str:
    """Expand Docker Hub's official-image shorthand before installer validation."""
    if re.fullmatch(r"caddy@sha256:[0-9a-f]{64}", image):
        image = "docker.io/library/" + image
    if not PINNED_IMAGE.fullmatch(image):
        raise ValueError("Caddy image must use an approved immutable sha256 digest and full registry path")
    return image


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
        cwd=root, check=True, env=controlled_environment(compose_file.parent, env_file),
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
        env=controlled_environment(compose_file.parent, custom_env),
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
        env=controlled_environment(compose_file.parent, identity_env),
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


def _container_http_response(
    compose_command: list[str],
    path: str,
    *,
    host: str | None = None,
    target: str = "api",
    env: dict[str, str],
) -> tuple[int, str]:
    """Probe the Compose network from the API container itself.

    Container-local probes avoid relying on host-published ports and test the
    actual API/UI servers on their service network. The disposable API also
    needs host-gateway access to reach the temporary HTTPS owner used by CI.
    """
    if target not in {"api", "ui"}:
        raise ValueError(f"Unsupported runtime smoke target: {target}")
    container_host = "127.0.0.1" if target == "api" else "ui"
    container_port = 8000 if target == "api" else 3010
    url = f"http://{container_host}:{container_port}{path}"
    script = textwrap.dedent("""
        import json, sys, urllib.error, urllib.request
        request = urllib.request.Request(sys.argv[1], headers={"Host": sys.argv[2]} if sys.argv[2] else {})
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                result = {"status": response.status, "body": response.read(4096).decode("utf-8", "replace")}
        except urllib.error.HTTPError as error:
            result = {"status": error.code, "body": error.read(4096).decode("utf-8", "replace") if error.fp else ""}
        print(json.dumps(result, separators=(",", ":")))
    """)
    response = subprocess.run(
        [*compose_command, "exec", "-T", "api", "python", "-c", script, url, host or ""],
        check=True, capture_output=True, text=True, timeout=20, env=env,
    )
    try:
        payload = json.loads(response.stdout.strip().splitlines()[-1])
        status = payload["status"]
        body = payload["body"]
    except (IndexError, KeyError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Container HTTP probe returned invalid response evidence") from exc
    if type(status) is not int or not isinstance(body, str):
        raise ValueError("Container HTTP probe returned invalid response evidence")
    return status, body


def _runtime_smoke_license(private_key: bytes, public_key: str) -> str:
    """Mint and locally verify a short-lived, domain-bound CI-only license."""
    from api.services.installation_license import issue_license_token, load_license

    issued_at = int(time.time())
    claims = {
        "iat": issued_at,
        "exp": issued_at + 3600,
        "installation_id": "ci-installation-smoke",
        "customer_id": "ci-smoke",
        "edition": "client",
        "domains": ["smoke.customer.example.invalid"],
        # The runtime smoke uses this to prove it enforces the signed owner's
        # IP-binding decision. The disposable peer simulates both decisions.
        "ip_ranges": ["192.0.2.0/24"],
        "features": ["voice"],
        "limits": {"max_concurrent_calls": 1, "max_seats": 1, "max_workspaces": 1},
    }
    token = issue_license_token(claims, private_key)
    parsed = load_license(token, public_key, now=issued_at)
    if parsed.installation_id != claims["installation_id"] or parsed.domains != tuple(claims["domains"]):
        raise ValueError("CI runtime license did not preserve its installation/domain binding")
    return token


def _prepare_ci_installation_key(api_image: str, owner: _OwnerAcceptanceServer, license_token: str) -> Path:
    """Use the built image's real helper to create and enroll a disposable identity."""
    from enroll_identity import _enrollment_url, _image_helper

    installation_key = secrets.token_bytes(32)
    common = {
        "license_token": license_token,
        "installation_id": owner.installation_id,
        "public_host": "smoke.customer.example.invalid",
        "private_key": base64.urlsafe_b64encode(installation_key).rstrip(b"=").decode("ascii"),
    }
    prepared = _image_helper(api_image, {
        **common, "action": "prepare_enrollment", "enrollment_token": owner.enrollment_token,
    })
    if prepared.get("owner_status_url") != owner.url:
        raise ValueError("Built API image is not pinned to the temporary HTTPS owner endpoint")
    enrollment_url = _enrollment_url(prepared["owner_status_url"])
    payload = {
        "enrollment_token": owner.enrollment_token,
        "public_key": prepared["public_key"],
        "nonce": prepared["nonce"],
        "issued_at": prepared["issued_at"],
        "signature": prepared["signature"],
    }
    # The owner server is also published on loopback for the verifier process;
    # the API container reaches the same listener through host-gateway routing.
    local_url = enrollment_url.replace("host.docker.internal", "127.0.0.1", 1)
    request = urllib.request.Request(
        local_url, data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {license_token}",
        },
    )
    context = ssl.create_default_context(cafile=str(owner.ca_file))
    with urllib.request.build_opener(urllib.request.HTTPSHandler(context=context)).open(request, timeout=10) as response:
        reply = json.loads(response.read(4096))
    if reply.get("enrolled") is not True or owner.public_key != prepared.get("public_key"):
        raise ValueError("Disposable owner did not confirm key enrollment")
    key_path = owner.ca_file.parent / "ci-installation.key"
    key_path.write_bytes(installation_key)
    key_path.chmod(0o640)
    gid = getattr(os, "getegid", lambda: 12345)()
    if not 1 <= gid <= 2**31 - 1:
        gid = 12345
        if hasattr(os, "chown"):
            os.chown(key_path, -1, gid)
    return key_path


def _verify_compose_runtime(
    root: Path,
    directory: Path,
    *,
    api_image: str,
    ui_image: str,
    manifest: Path,
    license_token: str,
    owner: _OwnerAcceptanceServer | None = None,
) -> dict[str, object]:
    """Start the built images with isolated dependencies and assert HTTP boundaries.

    With an owner peer, this exercises the real client identity proof and signed
    owner status over HTTPS. The fallback mode is kept for focused boundary tests.
    """
    project = f"kw-ci-{uuid.uuid4().hex[:12]}"
    minio_image = f"kodewaves-ci-minio:{project}"
    env_file = directory / f"{project}.env"
    compose_override = directory / f"{project}-internal-network.yaml"
    owner_trust_override = directory / f"{project}-owner-trust.yaml"
    compose_file = root / "deploy/client/docker-compose.client.yaml"
    api_port, ui_port, minio_port = secrets.SystemRandom().sample(range(20000, 60000), 3)
    values = {
        "CLIENT_API_IMAGE": api_image,
        "CLIENT_UI_IMAGE": ui_image,
        "CLIENT_POSTGRES_IMAGE": _CI_POSTGRES_IMAGE,
        "CLIENT_REDIS_IMAGE": _CI_REDIS_IMAGE,
        "CLIENT_MINIO_IMAGE": minio_image,
        # This service is not started by the selected api/ui dependency graph.
        "CLIENT_COTURN_IMAGE": "registry.invalid/kodewaves/coturn-ci@sha256:" + "0" * 64,
        "CLIENT_CADDY_IMAGE": "registry.invalid/kodewaves/caddy-ci@sha256:" + "0" * 64,
        "COMPOSE_PROFILES": "",
        "KODEWAVES_INSTALLATION_ID": "ci-installation-smoke",
        "KODEWAVES_LICENSE_TOKEN": license_token,
        "PUBLIC_HOST": "smoke.customer.example.invalid",
        "TURN_HOST": "8.8.8.8",
        "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
        "REDIS_PASSWORD": secrets.token_urlsafe(32),
        "MINIO_ROOT_USER": "kodewaves-ci-storage",
        "MINIO_ROOT_PASSWORD": secrets.token_urlsafe(32),
        "OSS_JWT_SECRET": secrets.token_urlsafe(32),
        "MASTER_CREDENTIAL_ENCRYPTION_KEY": base64.urlsafe_b64encode(
            secrets.token_bytes(32)
        ).rstrip(b"=").decode("ascii"),
        "TELEPHONY_WS_TOKEN_SECRET": secrets.token_urlsafe(32),
        "TURN_SECRET": secrets.token_urlsafe(32),
        "CLIENT_RELEASE_MANIFEST_FILE": str(manifest.resolve()),
        # Compose's `port` command needs an explicit published port; port 0
        # starts containers but yields no binding for the runtime smoke.
        "API_PORT": str(api_port),
        "UI_PORT": str(ui_port),
        "MINIO_PORT": str(minio_port),
    }
    identity_key = None
    identity_gid = None
    if owner is not None:
        identity_key = _prepare_ci_installation_key(api_image, owner, license_token)
        identity_gid = getattr(os, "getegid", lambda: 12345)()
        if not 1 <= identity_gid <= 2**31 - 1:
            identity_gid = 12345
            if hasattr(os, "chown"):
                os.chown(identity_key, -1, identity_gid)
        values.update(
            CLIENT_IDENTITY_KEY_FILE=str(identity_key.resolve()),
            CLIENT_IDENTITY_GID=str(identity_gid),
        )
    env_file.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    compose_override.write_text(
        "services:\n"
        "  api:\n"
        "    environment:\n"
        "      ARQ_WORKERS: \"0\"\n"
        "      ENABLE_ARI_MANAGER: \"false\"\n"
        "      ENABLE_CAMPAIGN_ORCHESTRATOR: \"false\"\n"
        "      KODEWAVES_OWNER_STATUS_POLL_SECONDS: \"1\"\n",
        encoding="utf-8",
    )
    if owner is not None:
        owner_trust_override.write_text(
            "services:\n"
            "  api:\n"
            "    environment:\n"
            "      SSL_CERT_FILE: /run/kodewaves-ci-owner/ca.pem\n"
            "    extra_hosts:\n"
            "      - host.docker.internal:host-gateway\n"
            "    volumes:\n"
            f"      - type: bind\n        source: {owner.ca_file.resolve()}\n"
            "        target: /run/kodewaves-ci-owner/ca.pem\n        read_only: true\n"
            "        bind:\n          create_host_path: false\n",
            encoding="utf-8",
        )
    compose_command = [
        "docker", "compose", "--project-name", project,
        "--env-file", str(env_file), "-f", str(compose_file),
        "-f", str(compose_override),
    ]
    if owner is not None:
        compose_command.extend(["-f", str(root / "deploy/client/docker-compose.identity.yaml"), "-f", str(owner_trust_override)])
    command_env = {**controlled_environment(compose_file.parent, env_file), "COMPOSE_PROFILES": ""}
    result: dict[str, object] = {}
    failure: BaseException | None = None
    try:
        subprocess.run(
            ["docker", "build", "--tag", minio_image, "--file",
             str(root / "deploy/minio/Dockerfile"), str(root / "deploy/minio")],
            cwd=root, check=True, env=command_env,
        )
        subprocess.run(
            [*compose_command, "up", "--detach", "--wait", "--wait-timeout", "300", "api", "ui"],
            # Capture Compose's startup diagnostics so a failed health wait can
            # be surfaced in the bounded GitHub Actions failure annotation.
            cwd=root, check=True, env=command_env, timeout=360,
            capture_output=True, text=True,
        )
        health_status, _ = _container_http_response(
            compose_command, "/api/v1/health", env=command_env,
        )
        if health_status != 200:
            raise ValueError(f"Packaged API health endpoint returned HTTP {health_status}")
        ui_status, _ = _container_http_response(
            compose_command, "/", target="ui", env=command_env,
        )
        if ui_status != 200:
            raise ValueError(f"Packaged UI root returned HTTP {ui_status}")
        wrong_host_status, wrong_host_body = _container_http_response(
            compose_command, "/api/v1/workflow",
            host="wrong.customer.example.invalid",
            env=command_env,
        )
        if wrong_host_status != 402 or "This domain is not licensed" not in wrong_host_body:
            raise ValueError(
                "A protected request with a mismatched Host must fail the signed domain binding; "
                f"received HTTP {wrong_host_status}: {wrong_host_body[:240]}"
            )
        valid_host_status, valid_host_body = _container_http_response(
            compose_command, "/api/v1/workflow",
            host="smoke.customer.example.invalid",
            env=command_env,
        )
        if owner is None and (
            valid_host_status != 402 or "Owner installation check has not succeeded" not in valid_host_body
        ):
            raise ValueError(
                "A correctly licensed Host must pass license validation and reach the owner-status gate; "
                f"received HTTP {valid_host_status}: {valid_host_body[:240]}"
            )
        if owner is not None:
            # Wait for the API's background signed owner poll to populate Redis.
            owner_gate_status, owner_gate_body = valid_host_status, valid_host_body
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                owner_gate_status, owner_gate_body = _container_http_response(
                    compose_command, "/api/v1/workflow",
                    host="smoke.customer.example.invalid",
                    env=command_env,
                )
                if owner_gate_status != 402:
                    break
                time.sleep(1)
            if owner_gate_status != 404 or "Not Found" not in owner_gate_body:
                raise ValueError(
                    "Enrolled owner status must pass licensing and reach the expected unauthenticated route boundary; "
                    f"received HTTP {owner_gate_status}: {owner_gate_body[:240]}"
                )
            # Exercise the client data-plane gate with a freshly signed owner
            # denial, then prove it recovers only after a fresh signed allow.
            owner.set_binding_valid(False)
            denied_status, denied_body = owner_gate_status, owner_gate_body
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                denied_status, denied_body = _container_http_response(
                    compose_command, "/api/v1/workflow",
                    host="smoke.customer.example.invalid",
                    env=command_env,
                )
                if denied_status == 402 and "outside the licensed ranges" in denied_body:
                    break
                time.sleep(0.25)
            if denied_status != 402 or "outside the licensed ranges" not in denied_body:
                raise ValueError(
                    "A fresh signed owner IP-binding denial must block protected API requests; "
                    f"received HTTP {denied_status}: {denied_body[:240]}"
                )
            owner.set_binding_valid(True)
            recovered_status, recovered_body = denied_status, denied_body
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                recovered_status, recovered_body = _container_http_response(
                    compose_command, "/api/v1/workflow",
                    host="smoke.customer.example.invalid",
                    env=command_env,
                )
                if recovered_status == 404 and "Not Found" in recovered_body:
                    break
                time.sleep(0.25)
            if recovered_status != 404 or "Not Found" not in recovered_body:
                raise ValueError(
                    "A fresh signed owner IP-binding allow must restore the normal API auth boundary; "
                    f"received HTTP {recovered_status}: {recovered_body[:240]}"
                )
            bootstrap_script = (
                "import asyncio,json,sys; from api.services.bootstrap_client_admin import bootstrap_client_admin; "
                "d=json.load(sys.stdin); i=asyncio.run(bootstrap_client_admin(d['email'],d['password'])); "
                "print(json.dumps({'administrator_id':i}))"
            )
            credentials = json.dumps({
                "email": "ci-owner@example.invalid", "password": secrets.token_urlsafe(32) + "Aa1!",
            })
            bootstrap = subprocess.run(
                [*compose_command, "exec", "-T", "api", "python", "-c", bootstrap_script],
                cwd=root, check=True, env=command_env, timeout=60,
                input=credentials, capture_output=True, text=True,
            )
            admin_data = json.loads(bootstrap.stdout.strip().splitlines()[-1])
            if type(admin_data.get("administrator_id")) is not int:
                raise ValueError("First-admin bootstrap did not return a created administrator")
            # Verify persisted owner privileges and workspace membership using
            # a stdin-driven script; credentials never appear in process argv.
            verify_admin_script = textwrap.dedent("""
                import asyncio, json
                from sqlalchemy import select
                from api.db import db_client
                from api.db.models import UserModel, organization_users_association

                async def main():
                    async with db_client.async_session() as session:
                        user = (await session.execute(
                            select(UserModel).where(UserModel.email == 'ci-owner@example.invalid')
                        )).scalar_one()
                        organizations = (await session.execute(
                            select(organization_users_association.c.organization_id).where(
                                organization_users_association.c.user_id == user.id
                            )
                        )).scalars().all()
                        print(json.dumps({
                            'is_superuser': user.is_superuser, 'active': user.is_active,
                            'workspace_memberships': len(organizations),
                        }))

                asyncio.run(main())
            """)
            admin_check = subprocess.run(
                [*compose_command, "exec", "-T", "api", "python", "-c", verify_admin_script],
                cwd=root, check=True, env=command_env, timeout=30, capture_output=True, text=True,
            )
            admin_evidence = json.loads(admin_check.stdout.strip().splitlines()[-1])
            if admin_evidence != {"is_superuser": True, "active": True, "workspace_memberships": 1}:
                raise ValueError("First-admin bootstrap did not create one active superuser with a workspace")
            repeat_bootstrap = subprocess.run(
                [*compose_command, "exec", "-T", "api", "python", "-c", bootstrap_script],
                cwd=root, check=False, env=command_env, timeout=60,
                input=credentials, capture_output=True, text=True,
            )
            if repeat_bootstrap.returncode == 0 or "only before the first account" not in (
                repeat_bootstrap.stdout + repeat_bootstrap.stderr
            ):
                raise ValueError("First-admin bootstrap must reject attempts after the first account exists")
            valid_host_status = owner_gate_status
        image_inspect = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", minio_image],
            check=True, capture_output=True, text=True,
        )
        result = {
            "api_health": "passed",
            "ui_root": "passed",
            "mismatched_host": "rejected_by_signed_domain_binding",
            "valid_host_owner_gate": (
                "license_accepted_owner_enrollment_required" if owner is None
                else f"owner_status_accepted_http_{valid_host_status}"
            ),
            "dependency_images": {
                "postgres": _CI_POSTGRES_IMAGE,
                "redis": _CI_REDIS_IMAGE,
                "minio_image_id": image_inspect.stdout.strip(),
            },
        }
        if owner is not None:
            result["ip_binding_denial_and_recovery"] = "rejected_false_binding_and_recovered_on_true_binding"
            result["owner_enrollment"] = "passed_signed_one_time_enrollment_and_status"
            result["first_admin_bootstrap"] = "passed_active_superuser_with_workspace"
            result["first_admin_replay"] = "rejected_after_initial_account"
    except BaseException as exc:
        failure = exc
        primary_output = ""
        if isinstance(exc, subprocess.CalledProcessError):
            primary_output = str(exc.stderr or exc.stdout or "").strip()
        diagnostics: list[str] = []
        if primary_output:
            diagnostics.append("Failing Compose output: " + primary_output[-420:])
        try:
            rendered = subprocess.run(
                [*compose_command, "config", "--format", "json"],
                cwd=root, check=False, env=command_env, timeout=30,
                capture_output=True, text=True,
            )
            if rendered.returncode == 0:
                config = json.loads(rendered.stdout)
                rendered_ports = {
                    name: service.get("ports", [])
                    for name, service in config.get("services", {}).items()
                    if name in {"api", "ui"}
                }
                diagnostics.append("Rendered Compose service ports: " + json.dumps(rendered_ports))
        except Exception as diagnostic_error:  # noqa: BLE001 - retain the original smoke failure
            diagnostics.append(f"Rendered Compose config diagnostic failed: {type(diagnostic_error).__name__}")
        try:
            status = subprocess.run(
                [*compose_command, "ps", "--all", "--format", "json", "api", "ui"],
                cwd=root, check=False, env=command_env, timeout=30,
                capture_output=True, text=True,
            )
            if status.stdout:
                service_status = status.stdout.strip()[-260:]
                diagnostics.append("Compose service state: " + service_status)
                print("Client runtime smoke service state: " + service_status, file=sys.stderr)
            logs = subprocess.run(
                [*compose_command, "logs", "--no-color", "--tail", "30", "api"],
                cwd=root, check=False, env=command_env, timeout=30,
                capture_output=True, text=True,
            )
            if logs.stdout:
                diagnostics.append("API startup log: " + logs.stdout.strip()[-360:])
            ui_logs = subprocess.run(
                [*compose_command, "logs", "--no-color", "--tail", "20", "ui"],
                cwd=root, check=False, env=command_env, timeout=30,
                capture_output=True, text=True,
            )
            if ui_logs.stdout:
                diagnostics.append("UI startup log: " + ui_logs.stdout.strip()[-300:])
        except Exception:  # noqa: BLE001 - preserve the failing smoke result
            diagnostics.append("Additional Compose diagnostics were unavailable")
        if diagnostics and isinstance(exc, subprocess.CalledProcessError):
            # Keep the original failing command output first, followed by
            # bounded state/log tails. The CI annotation can then retain the
            # cause instead of showing only logs gathered during diagnosis.
            exc.stderr = "\n".join(diagnostics)
        raise
    finally:
        cleanup_errors: list[str] = []
        try:
            down = subprocess.run(
                [*compose_command, "down", "--volumes", "--remove-orphans", "--timeout", "20"],
                cwd=root, check=False, env=command_env, timeout=60,
            )
            if down.returncode:
                cleanup_errors.append(f"compose_down={down.returncode}")
        except Exception as exc:  # noqa: BLE001 - continue cleanup of the remaining resources
            cleanup_errors.append(f"compose_down={type(exc).__name__}")
        try:
            image_cleanup = subprocess.run(
                ["docker", "image", "rm", "--force", minio_image],
                cwd=root, check=False, env=command_env, timeout=60,
            )
            if image_cleanup.returncode:
                cleanup_errors.append(f"minio_image_remove={image_cleanup.returncode}")
        except Exception as exc:  # noqa: BLE001 - preserve smoke failure and report cleanup failure
            cleanup_errors.append(f"minio_image_remove={type(exc).__name__}")
        if cleanup_errors and failure is None:
            raise RuntimeError(
                "Client runtime smoke cleanup failed: " + ", ".join(cleanup_errors)
            )
        if cleanup_errors:
            print(
                "Client runtime smoke cleanup warning: " + ", ".join(cleanup_errors),
                file=sys.stderr,
            )
    return result


def verify(caddy_image: str, report: Path) -> None:
    caddy_image = normalize_caddy_image(caddy_image)
    if report.exists():
        raise ValueError("Report already exists; use a new path for fresh verification")
    root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="kodewaves-ci-trust-") as temporary:
        directory = Path(temporary)
        if directory.resolve().is_relative_to(root):
            raise ValueError("Temporary signing keys must be outside the Docker build context")
        license_private, license_public = _temporary_keypair(directory, "license")
        release_private, release_public = _temporary_keypair(directory, "release")
        manifest = directory / "client-release-manifest.json"
        inventory_metrics_file = directory / "protected-inventory-metrics.json"
        api_image, ui_image = "kodewaves-client-api:ci-check", "kodewaves-client-ui:ci-check"
        license_token = _runtime_smoke_license(
            license_private.read_bytes(), license_public.read_text(encoding="ascii")
        )
        with _OwnerAcceptanceServer(
            directory, license_token, license_private.read_bytes(), license_public.read_text(encoding="ascii")
        ) as owner:
            subprocess.run([
                sys.executable, str(root / "deploy/client/build_and_verify.py"),
                "--api-tag", api_image, "--ui-tag", ui_image,
                "--caddy-image", caddy_image,
                "--license-public-key-file", str(license_public),
                "--release-public-key-file", str(release_public),
                "--owner-status-url", owner.url,
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
            runtime_smoke = _verify_compose_runtime(
                root, directory, api_image=api_image, ui_image=ui_image, manifest=manifest,
                license_token=license_token, owner=owner,
            )
        evidence = {
            "status": "passed", "production_release": False,
            "scope": "Client image boundaries, Caddy syntax, signed API/UI inventories, installer preflight, Compose interpolation, HTTPS owner enrollment, signed status, first-admin bootstrap, and disposable API/UI Compose runtime smoke",
            "installer_preflight": "passed", "compose_config": "passed",
            "installer_manifest_scope": "Unsigned configuration fixture; signed build inventories and image IDs verified separately",
            "custom_network_proxy_config": "passed",
            "identity_overlay_config": "passed",
            "startup_tamper_rejection": "passed",
            "runtime_compose_smoke": runtime_smoke,
            "protected_inventory": inventory_metrics,
            "not_verified": [
                "upgrade/rollback", "live owner alerts", "browser audio", "telephone",
            ],
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
    try:
        verify(args.caddy_image, args.report)
    except Exception as exc:
        if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
            # Surface a bounded summary when private action logs aren't visible;
            # include only the failing subprocess output, never the environment.
            detail = f"{type(exc).__name__}: {exc}"
            if isinstance(exc, subprocess.CalledProcessError):
                output = exc.stderr or exc.stdout
                if output:
                    # The full command often contains long temporary paths.
                    # Preserve its failure reason and the curated runtime
                    # diagnostics instead of truncating that reason away.
                    detail = f"{type(exc).__name__} (exit code {exc.returncode})\n{str(output)[:1050]}"
            detail = detail[:1200]
            detail = re.sub(
                r"(?i)(token|password|secret|api[_ -]?key|authorization)(\s*[:=]\s*)\S+",
                r"\1\2[REDACTED]",
                detail,
            )
            detail = detail.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::error title=Client image verification failed::{detail}", file=sys.stderr)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
