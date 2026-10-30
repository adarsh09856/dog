#!/usr/bin/env python3
"""Validate source-free client installer inputs before starting Compose."""

from __future__ import annotations

import argparse
import base64
import binascii
import ipaddress
import json
import os
import re
import stat
import sys
from pathlib import Path
from urllib.parse import urlsplit

IMAGE_KEYS = {
    "CLIENT_API_IMAGE",
    "CLIENT_UI_IMAGE",
    "CLIENT_POSTGRES_IMAGE",
    "CLIENT_REDIS_IMAGE",
    "CLIENT_MINIO_IMAGE",
    "CLIENT_COTURN_IMAGE",
    "CLIENT_CADDY_IMAGE",
}
PROFILE_IMAGE_KEYS = {"CLIENT_CADDY_IMAGE"}
DEFAULT_CLIENT_INTERNAL_SUBNET = "172.30.0.0/24"
DEFAULT_CLIENT_CADDY_IPV4 = "172.30.0.2"
SECRET_KEYS = {
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
    "MINIO_ROOT_PASSWORD",
    "OSS_JWT_SECRET",
    "TELEPHONY_WS_TOKEN_SECRET",
    "TURN_SECRET",
}
SAFE_SECRET = re.compile(r"^[A-Za-z0-9_-]{32,}$")
PINNED_IMAGE = re.compile(
    r"^[a-z0-9][a-z0-9.-]*(?::(?P<port>[0-9]{1,5}))?"
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+@sha256:[0-9a-f]{64}$"
)


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected KEY=value")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith("\"") and value.endswith("\"")) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError(f"{path}:{line_number}: invalid environment key {key!r}")
        values[key] = value
    return values


def validate_identity_key(env: dict[str, str]) -> list[str]:
    """Validate the optional host key shared read-only with API and UI."""
    key_file = env.get("CLIENT_IDENTITY_KEY_FILE", "").strip()
    group = env.get("CLIENT_IDENTITY_GID", "").strip()
    if not key_file and not group:
        return []
    if not key_file or not group:
        return ["CLIENT_IDENTITY_KEY_FILE and CLIENT_IDENTITY_GID must be set together"]
    if not re.fullmatch(r"[0-9]{1,10}", group) or not 1 <= int(group) <= 2**31 - 1:
        return ["CLIENT_IDENTITY_GID must be a nonzero numeric group ID"]
    if "$" in key_file:
        return ["CLIENT_IDENTITY_KEY_FILE must not contain Compose interpolation characters"]
    path = Path(key_file)
    if not path.is_absolute():
        return ["CLIENT_IDENTITY_KEY_FILE must be an absolute path"]
    try:
        metadata = path.lstat()
    except OSError:
        return ["CLIENT_IDENTITY_KEY_FILE must exist before starting the identity overlay"]
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != 32:
        return ["CLIENT_IDENTITY_KEY_FILE must be a regular 32-byte private key, not a symlink"]
    if os.name != "nt" and (
        metadata.st_gid != int(group) or stat.S_IMODE(metadata.st_mode) != 0o640
    ):
        return ["CLIENT_IDENTITY_KEY_FILE must have mode 0640, be owned by CLIENT_IDENTITY_GID, and be inaccessible to others"]
    return []


def validate(env_path: Path, compose_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        env = parse_env(env_path)
    except (OSError, ValueError) as exc:
        return [str(exc)]
    errors.extend(validate_identity_key(env))

    try:
        compose_text = compose_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"unable to read Compose file {compose_path}: {exc}"]
    compose_text = "\n".join(
        line for line in compose_text.splitlines()
        if not line.lstrip().startswith("#")
    )
    # The preflight only needs to discover required Compose interpolations.
    # Keep this script standard-library-only so a clean host can run it before
    # installing any Python packages; `docker compose config` validates YAML.
    required = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):\?", compose_text))

    profiles = {item.strip() for item in env.get("COMPOSE_PROFILES", "").split(",") if item.strip()}
    local_ports = {}
    for key, default in (("API_PORT", "8000"), ("UI_PORT", "3010"), ("MINIO_PORT", "9000")):
        value = env.get(key, "") or default
        if not re.fullmatch(r"[0-9]{1,5}", value) or not 1 <= int(value) <= 65535:
            errors.append(f"{key} must be a TCP port between 1 and 65535")
        else:
            local_ports[key] = int(value)
    if len(set(local_ports.values())) != len(local_ports):
        errors.append("API_PORT, UI_PORT and MINIO_PORT must be distinct")
    try:
        internal_network = ipaddress.ip_network(
            env.get("CLIENT_INTERNAL_SUBNET", DEFAULT_CLIENT_INTERNAL_SUBNET), strict=True
        )
        if internal_network.version != 4:
            raise ValueError("client network must use IPv4")
    except ValueError:
        internal_network = None
        errors.append("CLIENT_INTERNAL_SUBNET must be a valid IPv4 network address in CIDR form")

    try:
        caddy_ip = ipaddress.ip_address(
            env.get("CLIENT_CADDY_IPV4", DEFAULT_CLIENT_CADDY_IPV4)
        )
        if caddy_ip.version != 4:
            raise ValueError("Caddy address must use IPv4")
        if internal_network is None or caddy_ip not in internal_network or caddy_ip in {
            internal_network.network_address, internal_network.broadcast_address,
        }:
            errors.append("CLIENT_CADDY_IPV4 must be a usable address inside CLIENT_INTERNAL_SUBNET")
    except ValueError:
        caddy_ip = None
        errors.append("CLIENT_CADDY_IPV4 must be a valid IPv4 address")

    forwarded_value = env.get("FORWARDED_ALLOW_IPS", "").strip()
    if "direct-ingress" in profiles and not forwarded_value:
        forwarded_value = str(caddy_ip or DEFAULT_CLIENT_CADDY_IPV4)
    if not forwarded_value:
        errors.append("FORWARDED_ALLOW_IPS must identify the trusted reverse proxy address")
        forwarded_networks = []
    elif forwarded_value == "*" or any(value.strip() == "*" for value in forwarded_value.split(",")):
        errors.append("FORWARDED_ALLOW_IPS wildcard trust is unsafe; specify proxy IPs or CIDRs")
        forwarded_networks = []
    else:
        try:
            forwarded_networks = [
                ipaddress.ip_network(value.strip(), strict=False)
                for value in forwarded_value.split(",")
            ]
        except ValueError:
            errors.append("FORWARDED_ALLOW_IPS must contain only valid IP addresses or CIDRs")
            forwarded_networks = []

    if "direct-ingress" in profiles:
        if caddy_ip and (
            len(forwarded_networks) != 1
            or forwarded_networks[0].prefixlen != forwarded_networks[0].max_prefixlen
            or caddy_ip not in forwarded_networks[0]
        ):
            errors.append("FORWARDED_ALLOW_IPS must trust only the exact CLIENT_CADDY_IPV4 for direct-ingress")
    elif "FORWARDED_ALLOW_IPS" not in env or not env["FORWARDED_ALLOW_IPS"].strip():
        errors.append("FORWARDED_ALLOW_IPS must be explicitly set to the external proxy peer when direct-ingress is disabled")

    if "direct-ingress" not in profiles:
        required.discard("CLIENT_CADDY_IMAGE")
    elif not env.get("CLIENT_CADDY_IMAGE", "").strip():
        errors.append("CLIENT_CADDY_IMAGE is required when COMPOSE_PROFILES enables direct-ingress")
    for key in sorted(required):
        value = env.get(key, "")
        if not value:
            errors.append(f"{key} is required and must not be empty")
        elif "<" in value or ">" in value:
            errors.append(f"{key} still contains a template placeholder")

    selected_images = IMAGE_KEYS - (PROFILE_IMAGE_KEYS if "direct-ingress" not in profiles else set())
    for key in sorted(selected_images):
        value = env.get(key, "")
        if value:
            match = PINNED_IMAGE.fullmatch(value)
            if not match:
                errors.append(f"{key} must be an image reference pinned to a full lowercase sha256 digest")
            elif match.group("port") and not 1 <= int(match.group("port")) <= 65535:
                errors.append(f"{key} registry port must be between 1 and 65535")

    installation_id = env.get("KODEWAVES_INSTALLATION_ID", "")
    if installation_id and "<" not in installation_id and ">" not in installation_id and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,99}", installation_id):
        errors.append("KODEWAVES_INSTALLATION_ID must be 3–100 URL-safe identifier characters")

    license_token = env.get("KODEWAVES_LICENSE_TOKEN", "")
    if license_token and "<" not in license_token and ">" not in license_token and not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", license_token):
        errors.append("KODEWAVES_LICENSE_TOKEN must have the signed payload.signature form")

    host = env.get("PUBLIC_HOST", "")
    if host and ("<" not in host and ">" not in host):
        parsed = urlsplit(f"//{host}")
        hostname = parsed.hostname or ""
        try:
            has_port = parsed.port is not None
        except ValueError:
            has_port = True
        if parsed.path or parsed.query or parsed.fragment or has_port or "@" in host or "," in host or "{" in host or "}" in host or "\n" in host or "\r" in host:
            errors.append("PUBLIC_HOST must be a hostname only, without scheme, port or path")
        else:
            try:
                ascii_hostname = hostname.encode("idna").decode("ascii").lower()
            except UnicodeError:
                ascii_hostname = ""
            labels = ascii_hostname.rstrip(".").split(".")
            if not ascii_hostname or len(ascii_hostname) > 253 or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in labels
            ):
                errors.append("PUBLIC_HOST must be a valid DNS hostname")

    turn_host = env.get("TURN_HOST", "")
    if turn_host and "<" not in turn_host and ">" not in turn_host:
        try:
            turn_address = ipaddress.ip_address(turn_host)
        except ValueError:
            errors.append("TURN_HOST must be a public IPv4 address, without a URL or port")
        else:
            if not turn_address.is_global:
                errors.append("TURN_HOST must be a globally routable public IPv4 address")
            elif turn_address.version != 4:
                errors.append("TURN_HOST must be a public IPv4 address; this installer does not configure IPv6 TURN")

    server_ip = env.get("SERVER_IP", "")
    if server_ip and "<" not in server_ip and ">" not in server_ip:
        try:
            ipaddress.ip_address(server_ip)
        except ValueError:
            errors.append("SERVER_IP must be an IPv4 or IPv6 address when set")

    for key in sorted(SECRET_KEYS):
        value = env.get(key, "")
        if value and "<" not in value and ">" not in value and not SAFE_SECRET.fullmatch(value):
            errors.append(f"{key} must contain at least 32 URL-safe characters (A-Z, a-z, 0-9, _ or -)")

    credential_key = env.get("MASTER_CREDENTIAL_ENCRYPTION_KEY", "")
    if credential_key and "<" not in credential_key and ">" not in credential_key:
        try:
            # A 32-byte Fernet key has 43 URL-safe Base64 characters, optionally
            # followed by one padding character. Validate the alphabet before
            # decoding: urlsafe_b64decode silently discards arbitrary characters.
            if not re.fullmatch(r"[A-Za-z0-9_-]{43}=?", credential_key):
                raise ValueError
            decoded = base64.b64decode(
                credential_key + "=" * (-len(credential_key) % 4),
                altchars=b"-_",
                validate=True,
            )
            if len(decoded) != 32:
                raise ValueError
        except (ValueError, binascii.Error):
            errors.append("MASTER_CREDENTIAL_ENCRYPTION_KEY must be URL-safe base64 for exactly 32 random bytes")

    manifest = env.get("CLIENT_RELEASE_MANIFEST_FILE", "")
    if manifest and "<" not in manifest and ">" not in manifest:
        manifest_path = (env_path.parent / manifest).resolve()
        if not manifest_path.is_file():
            errors.append(f"signed release manifest does not exist: {manifest_path}")
        else:
            try:
                signed = json.loads(manifest_path.read_text(encoding="utf-8"))
                payload = signed.get("payload") if isinstance(signed, dict) else None
                if not isinstance(payload, dict):
                    errors.append("signed release manifest must contain a payload object")
                else:
                    images = payload.get("images")
                    # Older signed manifests may omit the inventory. If they include it,
                    # require both protected images and exact digest references so a
                    # partial inventory cannot pass preflight and fail only at startup.
                    if images is not None:
                        if not isinstance(images, dict) or set(images) != {"api", "ui"}:
                            errors.append("signed release manifest must contain API and UI image entries")
                        else:
                            for component, variable in (("api", "CLIENT_API_IMAGE"), ("ui", "CLIENT_UI_IMAGE")):
                                image = images[component]
                                if (
                                    not isinstance(image, dict)
                                    or image.get("kind") != "registry_digest"
                                    or image.get("reference") != env.get(variable)
                                ):
                                    errors.append(f"{variable} does not match the signed release manifest")
            except (OSError, ValueError, AttributeError):
                errors.append("signed release manifest must contain valid JSON")

    if not errors:
        # Ensure the Compose document itself parses and interpolates with these values.
        # Docker Compose performs the final interpolation and schema validation.
        errors.append("preflight passed; run docker compose config --quiet for Compose validation and API startup to verify signed license and manifest")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--compose-file", type=Path, default=Path(__file__).with_name("docker-compose.client.yaml"))
    args = parser.parse_args()
    results = validate(args.env_file, args.compose_file)
    failures = [item for item in results if not item.startswith("preflight passed;")]
    if failures:
        for item in failures:
            print(f"ERROR: {item}", file=sys.stderr)
        return 1
    print("Client installation inputs look valid.")
    print(results[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
