#!/usr/bin/env python3
"""Create a customer-only installation archive from an owner-approved release."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import re
import sys
import tarfile
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy/client"))
from build_and_verify import read_public_key
from validate_install import IMAGE_KEYS, PINNED_IMAGE, parse_env


def package_installer(
    images_env: Path,
    manifest: Path,
    public_key_file: Path,
    output: Path,
    *,
    root: Path = ROOT,
) -> None:
    """Ship only allowlisted installation files, never keys or runtime secrets."""
    if output.exists():
        raise ValueError("Installer archive already exists; choose a new output path")
    images = parse_env(images_env)
    if set(images) != IMAGE_KEYS:
        raise ValueError("Image input must contain exactly the seven CLIENT_*_IMAGE values and no secrets")
    if any(not PINNED_IMAGE.fullmatch(value) for value in images.values()):
        raise ValueError("Every installer image must use an approved immutable sha256 digest")
    for value in images.values():
        port = PINNED_IMAGE.fullmatch(value).group("port")
        if port and not 1 <= int(port) <= 65535:
            raise ValueError("Installer image registry port must be between 1 and 65535")

    public_key = read_public_key(public_key_file)
    manifest_bytes = manifest.read_bytes()
    signed = json.loads(manifest_bytes)
    payload = signed.get("payload") if isinstance(signed, dict) else None
    if not isinstance(payload, dict) or payload.get("edition") != "client":
        raise ValueError("Release manifest must contain a client payload")
    signature = signed.get("signature")
    if not isinstance(signature, str) or not re.fullmatch(r"[A-Za-z0-9_-]{86}", signature):
        raise ValueError("Release manifest signature is invalid")
    raw_key = base64.urlsafe_b64decode(public_key + "=" * (-len(public_key) % 4))
    raw_signature = base64.urlsafe_b64decode(signature + "==")
    if base64.urlsafe_b64encode(raw_signature).rstrip(b"=").decode("ascii") != signature:
        raise ValueError("Release manifest signature is invalid")
    try:
        Ed25519PublicKey.from_public_bytes(raw_key).verify(
            raw_signature,
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        )
    except InvalidSignature as exc:
        raise ValueError("Release manifest signature is invalid") from exc
    signed_images = payload.get("images")
    if not isinstance(signed_images, dict) or set(signed_images) != {"api", "ui"}:
        raise ValueError("Release manifest must contain exactly the signed API and UI images")
    for component, variable in (("api", "CLIENT_API_IMAGE"), ("ui", "CLIENT_UI_IMAGE")):
        expected = {"kind": "registry_digest", "reference": images[variable]}
        if signed_images.get(component) != expected:
            raise ValueError(f"Signed {component.upper()} image does not match the installer digest")
    if not all(isinstance(payload.get(key), dict) and payload[key] for key in ("files", "ui_files")):
        raise ValueError("Release manifest must contain nonempty API and UI inventories")
    for inventory in (payload["files"], payload["ui_files"]):
        if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in inventory.values()):
            raise ValueError("Release manifest contains an invalid inventory digest")
    schema = payload.get("schema_compatibility")
    if (
        not isinstance(schema, dict)
        or not isinstance(schema.get("head"), str)
        or not isinstance(schema.get("upgrade_from"), list)
        or not isinstance(schema.get("rollback_to"), list)
        or not all(
            isinstance(revision, str) and re.fullmatch(r"[A-Za-z0-9_]{1,64}", revision)
            for revision in [schema["head"], *schema["upgrade_from"], *schema["rollback_to"]]
        )
        or schema["head"] not in schema["upgrade_from"]
        or len(set(schema["upgrade_from"])) != len(schema["upgrade_from"])
        or len(set(schema["rollback_to"])) != len(schema["rollback_to"])
        or not set(schema["rollback_to"]).issubset(schema["upgrade_from"])
    ):
        raise ValueError("Release manifest must contain valid signed schema compatibility metadata")

    directory = root / "deploy/client"
    env_template = (directory / ".env.example").read_text(encoding="utf-8")
    for variable, value in images.items():
        env_template, replacements = re.subn(
            rf"^{variable}=.*$", f"{variable}={value}", env_template, flags=re.MULTILINE,
        )
        if replacements != 1:
            raise ValueError(f"Installer template must define {variable} exactly once")

    # Reading only these fixed paths prevents caller-selected sources, archive
    # traversal names, local .env files or private signing tools from shipping.
    files = {
        "README.md": (directory / "INSTALL.md").read_bytes(),
        "docker-compose.client.yaml": (directory / "docker-compose.client.yaml").read_bytes(),
        "docker-compose.identity.yaml": (directory / "docker-compose.identity.yaml").read_bytes(),
        "Caddyfile": (directory / "Caddyfile").read_bytes(),
        "validate_install.py": (directory / "validate_install.py").read_bytes(),
        "enroll_identity.py": (directory / "enroll_identity.py").read_bytes(),
        ".env.example": env_template.encode("utf-8"),
        "client-release-manifest.json": manifest_bytes,
        "release-public-key.txt": (public_key + "\n").encode("ascii"),
    }
    files["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name, content in sorted(files.items())
    ).encode("ascii")
    archive = io.BytesIO()
    # Fix gzip metadata and use a simple tar format so identical approved inputs
    # produce byte-for-byte identical customer archives and delivery checksums.
    with gzip.GzipFile(fileobj=archive, mode="wb", filename="", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as bundle:
            for name, content in sorted(files.items()):
                entry = tarfile.TarInfo(name)
                entry.size = len(content)
                entry.mode = 0o600 if name == ".env.example" else 0o644
                bundle.addfile(entry, io.BytesIO(content))
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids overwriting an existing package even if another
    # process created it while signature verification was running.
    with output.open("xb") as destination:
        destination.write(archive.getvalue())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images-env", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--release-public-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    package_installer(args.images_env, args.manifest, args.release_public_key, args.output)
    print(f"Customer installation archive written: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
