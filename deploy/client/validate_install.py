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
MODEL_IMAGE_KEYS = {
    "CLIENT_OLLAMA_IMAGE", "CLIENT_INDIC_STT_IMAGE",
    "CLIENT_INDUS_TTS_IMAGE", "CLIENT_INDIC_VITS_TTS_IMAGE",
}
MODEL_IMAGE_COMPONENTS = {
    "ollama": "CLIENT_OLLAMA_IMAGE",
    "indic_stt": "CLIENT_INDIC_STT_IMAGE",
    "indus_tts": "CLIENT_INDUS_TTS_IMAGE",
    "indic_vits_tts": "CLIENT_INDIC_VITS_TTS_IMAGE",
}
MODEL_ASSET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}")
MODEL_ASSET_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
MODEL_ASSET_ENV_KEYS = {"CLIENT_OLLAMA_MODEL", "CLIENT_OLLAMA_MODEL_DIGEST"}


def validate_model_images(images: dict[str, str]) -> None:
    """Model pins are either absent or a complete, immutable inference stack."""
    # The customer .env template carries blank optional pins for cloud-only
    # installs. Treat blank as absent; any partial nonblank set is invalid.
    supplied = {key for key in MODEL_IMAGE_KEYS if images.get(key, "").strip()}
    if supplied and supplied != MODEL_IMAGE_KEYS:
        raise ValueError("Local inference requires all four approved model image digests")
    for key in supplied:
        if not PINNED_IMAGE.fullmatch(images[key]):
            raise ValueError(f"{key} must use an immutable sha256 image reference")


def validate_model_asset(payload: dict, env: dict[str, str], *, self_hosted: bool) -> list[str]:
    """Check customer model selection against its optional owner-signed digest."""
    errors: list[str] = []
    model_assets = payload.get("model_assets")
    if model_assets is None:
        if self_hosted:
            errors.append("signed release manifest is missing the self-hosted Ollama model asset")
        return errors

    descriptor = model_assets.get("ollama") if isinstance(model_assets, dict) else None
    if (
        not isinstance(model_assets, dict)
        or set(model_assets) != {"ollama"}
        or not isinstance(descriptor, dict)
        or set(descriptor) != {"name", "digest"}
        or not isinstance(descriptor.get("name"), str)
        or not MODEL_ASSET_NAME.fullmatch(descriptor["name"])
        or not isinstance(descriptor.get("digest"), str)
        or not MODEL_ASSET_DIGEST.fullmatch(descriptor["digest"])
    ):
        errors.append("signed release manifest has invalid Ollama model asset metadata")
    elif self_hosted and (
        env.get("CLIENT_OLLAMA_MODEL", "").strip() != descriptor["name"]
        or env.get("CLIENT_OLLAMA_MODEL_DIGEST", "").strip() != descriptor["digest"]
    ):
        errors.append("CLIENT_OLLAMA_MODEL and CLIENT_OLLAMA_MODEL_DIGEST must match the signed release manifest")
    return errors

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


def validate_release_image_inventory(images: dict[str, str]) -> set[str]:
    """Validate the exact cloud or self-hosted release image profile.

    The signed customer env also carries the selected model name and weights
    digest. Those values are metadata, not Docker references, so validate them
    independently from the container image pins.
    """
    image_keys = set(images) - MODEL_ASSET_ENV_KEYS
    validate_model_images(images)
    cloud_profile = IMAGE_KEYS
    self_hosted_profile = IMAGE_KEYS | MODEL_IMAGE_KEYS
    if image_keys not in (cloud_profile, self_hosted_profile):
        raise ValueError("release image inventory does not match an approved profile")

    metadata_keys = set(images) & MODEL_ASSET_ENV_KEYS
    if image_keys == self_hosted_profile:
        if metadata_keys != MODEL_ASSET_ENV_KEYS:
            raise ValueError("self-hosted release requires complete model asset metadata")
        if (
            not MODEL_ASSET_NAME.fullmatch(images["CLIENT_OLLAMA_MODEL"])
            or not MODEL_ASSET_DIGEST.fullmatch(images["CLIENT_OLLAMA_MODEL_DIGEST"])
        ):
            raise ValueError("self-hosted release has invalid model asset metadata")
    elif metadata_keys:
        raise ValueError("cloud release must not contain self-hosted model metadata")

    for name in image_keys:
        if not PINNED_IMAGE.fullmatch(images[name]):
            raise ValueError(f"{name} is not an immutable sha256 image reference")
    return image_keys


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
    if "self-hosted" in profiles:
        model_compose = compose_path.with_name("docker-compose.models.yaml")
        if not model_compose.is_file() or model_compose.is_symlink():
            errors.append("The approved docker-compose.models.yaml is required for self-hosted inference")
        required.update(MODEL_IMAGE_KEYS)
        try:
            budget = int(env.get("CLIENT_SELF_HOSTED_MEMORY_GIB", "16"))
            if budget < 16:
                raise ValueError
        except ValueError:
            errors.append("Self-hosted inference requires a memory budget of at least 16 GiB; use connected inference on smaller hosts")
        try:
            validate_model_images({key: env.get(key, "") for key in MODEL_IMAGE_KEYS})
        except ValueError as exc:
            errors.append(str(exc))
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
    if "self-hosted" in profiles:
        selected_images |= MODEL_IMAGE_KEYS
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
    for key_name, key_value in (
        ("MASTER_CREDENTIAL_ENCRYPTION_KEY", credential_key),
        ("MASTER_CREDENTIAL_ENCRYPTION_KEY_PREVIOUS", env.get("MASTER_CREDENTIAL_ENCRYPTION_KEY_PREVIOUS", "")),
    ):
        if not key_value or "<" in key_value or ">" in key_value:
            continue
        for candidate in key_value.split(","):
            candidate = candidate.strip()
            if (
                key_name == "MASTER_CREDENTIAL_ENCRYPTION_KEY_PREVIOUS"
                and candidate.startswith("legacy:")
            ):
                # Installer upgrades may preserve older JWT-derived keys as
                # read-only entries. They are arbitrary old secrets, not Fernet
                # keys, and must never be accepted as the current write key.
                if not candidate.removeprefix("legacy:").strip():
                    errors.append(
                        f"{key_name} must not contain an empty legacy key"
                    )
                    break
                continue
            if (
                key_name == "MASTER_CREDENTIAL_ENCRYPTION_KEY_PREVIOUS"
                and candidate.startswith("legacy-b64:")
            ):
                encoded_secret = candidate.removeprefix("legacy-b64:")
                try:
                    if not re.fullmatch(r"[A-Za-z0-9_-]+", encoded_secret):
                        raise ValueError
                    decoded_secret = base64.b64decode(
                        encoded_secret + "=" * (-len(encoded_secret) % 4),
                        altchars=b"-_",
                        validate=True,
                    ).decode("utf-8")
                    if not decoded_secret:
                        raise ValueError
                except (ValueError, UnicodeDecodeError, binascii.Error):
                    errors.append(
                        f"{key_name} contains an invalid base64url-encoded legacy key"
                    )
                    break
                continue
            try:
                # Fernet accepts URL-safe Base64 encodings of exactly 32 bytes.
                # Validate the alphabet before decoding because urlsafe_b64decode
                # otherwise silently discards malformed characters.
                # Python Fernet keys may omit their optional trailing padding.
                if not re.fullmatch(r"[A-Za-z0-9_-]{43}=?", candidate):
                    raise ValueError
                decoded = base64.b64decode(
                    candidate + "=" * (-len(candidate) % 4),
                    altchars=b"-_",
                    validate=True,
                )
                if len(decoded) != 32:
                    raise ValueError
            except (ValueError, binascii.Error):
                errors.append(f"{key_name} must contain comma-separated URL-safe base64 Fernet keys for exactly 32 random bytes")
                break

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
                    model_images = payload.get("model_images")
                    configured_model_keys = {
                        key for key in MODEL_IMAGE_KEYS if env.get(key, "").strip()
                    }
                    self_hosted = "self-hosted" in profiles
                    if model_images is not None:
                        if (
                            images is None
                            or not isinstance(model_images, dict)
                            or set(model_images) != set(MODEL_IMAGE_COMPONENTS)
                        ):
                            errors.append("signed release manifest must contain all four model image entries")
                        else:
                            for component, variable in MODEL_IMAGE_COMPONENTS.items():
                                reference = model_images.get(component)
                                if not isinstance(reference, str) or not PINNED_IMAGE.fullmatch(reference):
                                    errors.append(f"signed release manifest has an invalid {component} model image")
                                elif (self_hosted or configured_model_keys) and env.get(variable, "").strip() != reference:
                                    errors.append(f"{variable} does not match the signed release manifest")
                    elif self_hosted or configured_model_keys:
                        errors.append("signed release manifest is missing the configured model image inventory")
                    errors.extend(validate_model_asset(payload, env, self_hosted=self_hosted))
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
