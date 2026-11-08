#!/usr/bin/env python3
"""Create a customer-only installation archive from an owner-approved release."""

from __future__ import annotations

import argparse
import base64
import binascii
import gzip
import hashlib
import io
import json
import re
import sys
import tarfile
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy/client"))
from build_and_verify import read_public_key, validate_owner_private_key_path
from validate_install import IMAGE_KEYS, MODEL_IMAGE_KEYS, PINNED_IMAGE, parse_env, validate_model_images
from verify_installer import MAX_INSTALLER_ARCHIVE_BYTES

MODEL_IMAGE_COMPONENTS = {
    "ollama": "CLIENT_OLLAMA_IMAGE",
    "indic_stt": "CLIENT_INDIC_STT_IMAGE",
    "indus_tts": "CLIENT_INDUS_TTS_IMAGE",
    "indic_vits_tts": "CLIENT_INDIC_VITS_TTS_IMAGE",
}
OLLAMA_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}")
OLLAMA_MODEL_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
SILO_RELEASE = "RELEASE.2026-10-26T00-00-00Z"
SILO_IMAGE = "docker.io/pgsty/silo@sha256:7bb2aff6b89efe1cb1303c10fc21d579447434ed06649ac9ec05a5e2dbf30ad7"
SILO_SOURCE_ARCHIVE_NAME = f"silo-source-{SILO_RELEASE}.tar.gz"
SILO_SOURCE_SHA256 = "011653445e59b3d9f01ca482a41e1706ba214d5cac4c254b43543b4fe8d209fc"
SILO_LICENSE_SHA256 = "0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0"
SILO_NOTICE_SHA256 = "16026398077eccabc3ca66db98af0a295d42ba3fdb8c0c2ad1339f4bdd33099e"
SILO_CREDITS_SHA256 = "00d51bcb05cc6c2c16c2f0a8866b9113eca7a4dbcce9d0a90893ee932fb5ce39"


def _read_canonical_text(path: Path) -> bytes:
    """Read tracked attribution text consistently across LF/CRLF checkouts."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def package_installer(
    images_env: Path,
    manifest: Path,
    public_key_file: Path,
    private_key_file: Path | None,
    output: Path | None = None,
    *,
    root: Path = ROOT,
    silo_source_archive: Path | None = None,
    allow_test_object_store: bool = False,
) -> None:
    """Ship only allowlisted installation files, never keys or runtime secrets.

    Supplying the signing key is mandatory for production releases. The older
    four-path form remains available only for isolated archive-structure checks;
    it produces a legacy archive without updater assets or a detached signature.
    """
    unsigned_legacy_package = output is None
    if unsigned_legacy_package:
        output = private_key_file
        private_key_file = None
    if output is None:  # Defensive narrowing for type checkers and callers.
        raise ValueError("Installer output path is required")
    if unsigned_legacy_package and root.resolve() == ROOT.resolve():
        raise ValueError("Owner release private key is required for production installer packages")
    signature_output = output.with_name(output.name + ".sig")
    if output.exists() or signature_output.exists():
        raise ValueError("Installer archive already exists; choose a new output path")
    if private_key_file is not None:
        private_key_file = validate_owner_private_key_path(private_key_file, ROOT)
    input_values = parse_env(images_env)
    configured_model_name = input_values.pop("CLIENT_OLLAMA_MODEL", None)
    configured_model_digest = input_values.pop("CLIENT_OLLAMA_MODEL_DIGEST", None)
    if configured_model_name is not None and not OLLAMA_MODEL_NAME.fullmatch(configured_model_name):
        raise ValueError("CLIENT_OLLAMA_MODEL must be a valid Ollama model identifier")
    if configured_model_digest is not None and not OLLAMA_MODEL_DIGEST.fullmatch(configured_model_digest):
        raise ValueError("CLIENT_OLLAMA_MODEL_DIGEST must be a sha256 digest")
    images = {
        key: value for key, value in input_values.items()
        if key not in MODEL_IMAGE_KEYS or value.strip()
    }
    if set(images) not in (IMAGE_KEYS, IMAGE_KEYS | MODEL_IMAGE_KEYS):
        raise ValueError("Image input must contain the seven infrastructure images, optionally all four local inference images, and no secrets")
    validate_model_images(images)
    if any(not PINNED_IMAGE.fullmatch(value) for value in images.values()):
        raise ValueError("Every installer image must use an approved immutable sha256 digest")
    for value in images.values():
        port = PINNED_IMAGE.fullmatch(value).group("port")
        if port and not 1 <= int(port) <= 65535:
            raise ValueError("Installer image registry port must be between 1 and 65535")

    source_bytes: bytes | None = None
    if images["CLIENT_MINIO_IMAGE"] == SILO_IMAGE or allow_test_object_store:
        if silo_source_archive is None:
            silo_source_archive = root / "deploy/client/third-party" / SILO_SOURCE_ARCHIVE_NAME
        if (
            silo_source_archive.is_symlink()
            or not silo_source_archive.is_file()
            or silo_source_archive.stat().st_size > MAX_INSTALLER_ARCHIVE_BYTES
        ):
            raise ValueError("PGSTY Silo source archive is not a supported regular file")
        source_bytes = silo_source_archive.read_bytes()
        if hashlib.sha256(source_bytes).hexdigest() != SILO_SOURCE_SHA256:
            raise ValueError("PGSTY Silo source archive does not match the approved release checksum")
        third_party_files = {
            "AGPL-3.0-PGSTY-Silo.txt": _read_canonical_text(root / "deploy/client/third-party/AGPL-3.0-PGSTY-Silo.txt"),
            "PGSTY-Silo-NOTICE.txt": _read_canonical_text(root / "deploy/client/third-party/NOTICE"),
            "PGSTY-Silo-CREDITS.txt": _read_canonical_text(root / "deploy/client/third-party/CREDITS"),
            "THIRD_PARTY_NOTICES.txt": _read_canonical_text(root / "deploy/client/third-party/THIRD_PARTY_NOTICES.txt"),
        }
        expected_digests = {
            "AGPL-3.0-PGSTY-Silo.txt": SILO_LICENSE_SHA256,
            "PGSTY-Silo-NOTICE.txt": SILO_NOTICE_SHA256,
            "PGSTY-Silo-CREDITS.txt": SILO_CREDITS_SHA256,
        }
        if any(hashlib.sha256(third_party_files[name]).hexdigest() != expected for name, expected in expected_digests.items()):
            raise ValueError("PGSTY Silo license or attribution file does not match the approved release")
        if SILO_SOURCE_SHA256.encode("ascii") not in third_party_files["THIRD_PARTY_NOTICES.txt"]:
            raise ValueError("PGSTY Silo third-party notice does not identify the matching source archive")
        third_party_files[SILO_SOURCE_ARCHIVE_NAME] = source_bytes
    else:
        raise ValueError("Customer releases must use the approved PGSTY Silo object-storage image digest")

    public_key = read_public_key(public_key_file)
    private_key = None
    if private_key_file is not None:
        private_key_bytes = private_key_file.read_bytes()
        if len(private_key_bytes) != 32:
            try:
                encoded_key = private_key_bytes.decode("ascii").strip()
                if not re.fullmatch(r"[A-Za-z0-9_-]{43}=?", encoded_key):
                    raise ValueError("invalid encoding")
                private_key_bytes = base64.b64decode(
                    encoded_key + "=" * (-len(encoded_key) % 4), altchars=b"-_", validate=True,
                )
                if (
                    len(private_key_bytes) != 32
                    or base64.urlsafe_b64encode(private_key_bytes).rstrip(b"=").decode("ascii")
                    != encoded_key.rstrip("=")
                ):
                    raise ValueError("non-canonical key")
            except (UnicodeDecodeError, ValueError, binascii.Error) as exc:
                raise ValueError("Owner release private key must be 32 raw bytes or canonical URL-safe Base64") from exc
        private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    trusted_public_key_raw = base64.urlsafe_b64decode(
        public_key + "=" * (-len(public_key) % 4)
    )
    if private_key is not None:
        derived_public = base64.urlsafe_b64encode(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        ).rstrip(b"=").decode("ascii")
        if derived_public != base64.urlsafe_b64encode(trusted_public_key_raw).rstrip(b"=").decode("ascii"):
            raise ValueError("Release private key does not match the trusted public key")
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
    signed_model_images = payload.get("model_images")
    signed_model_assets = payload.get("model_assets")
    if signed_model_assets is not None:
        if (
            not isinstance(signed_model_assets, dict)
            or set(signed_model_assets) != {"ollama"}
            or not isinstance(signed_model_assets["ollama"], dict)
            or set(signed_model_assets["ollama"]) != {"name", "digest"}
            or not isinstance(signed_model_assets["ollama"].get("name"), str)
            or not OLLAMA_MODEL_NAME.fullmatch(signed_model_assets["ollama"]["name"])
            or not isinstance(signed_model_assets["ollama"].get("digest"), str)
            or not OLLAMA_MODEL_DIGEST.fullmatch(signed_model_assets["ollama"]["digest"])
        ):
            raise ValueError("Release manifest Ollama model asset must contain exactly a valid name and sha256 digest")
    configured_model_images = {
        component: images[variable]
        for component, variable in MODEL_IMAGE_COMPONENTS.items()
        if variable in images
    }
    if configured_model_images:
        if set(configured_model_images) != set(MODEL_IMAGE_COMPONENTS):
            raise ValueError("Installer must configure either no local inference images or all four")
        if not isinstance(signed_model_images, dict) or set(signed_model_images) != set(MODEL_IMAGE_COMPONENTS):
            raise ValueError("Release manifest must sign the exact four configured local inference images")
        if signed_model_images != configured_model_images:
            raise ValueError("Signed model image digests do not match the installer image pins")
        if signed_model_assets is None:
            raise ValueError("Self-hosted installer requires the signed Ollama model asset digest")
    elif signed_model_images is not None:
        if not isinstance(signed_model_images, dict) or set(signed_model_images) != set(MODEL_IMAGE_COMPONENTS):
            raise ValueError("Release manifest model inventory must contain exactly four local inference images")
        if not all(isinstance(value, str) and PINNED_IMAGE.fullmatch(value) for value in signed_model_images.values()):
            raise ValueError("Release manifest model inventory must use immutable image digests")
    if configured_model_name is not None and not configured_model_images:
        raise ValueError("CLIENT_OLLAMA_MODEL is only valid when all local inference images are configured")
    if configured_model_digest is not None and not configured_model_images:
        raise ValueError("CLIENT_OLLAMA_MODEL_DIGEST is only valid when all local inference images are configured")
    template_model_match = re.search(r"^CLIENT_OLLAMA_MODEL=([^\r\n]*)$", (root / "deploy/client/.env.example").read_text(encoding="utf-8"), re.MULTILINE)
    if not template_model_match:
        raise ValueError("Installer template must define CLIENT_OLLAMA_MODEL exactly once")
    installer_model_name = configured_model_name or template_model_match.group(1)
    if signed_model_assets is not None and signed_model_assets["ollama"]["name"] != installer_model_name:
        raise ValueError("Signed Ollama model name does not match the installer model configuration")
    signed_model_digest = signed_model_assets["ollama"]["digest"] if signed_model_assets is not None else None
    if configured_model_digest is not None and configured_model_digest != signed_model_digest:
        raise ValueError("Signed Ollama model digest does not match the installer model configuration")
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
    if configured_model_name is not None:
        env_template, replacements = re.subn(
            r"^CLIENT_OLLAMA_MODEL=.*$",
            f"CLIENT_OLLAMA_MODEL={configured_model_name}",
            env_template,
            flags=re.MULTILINE,
        )
        if replacements != 1:
            raise ValueError("Installer template must define CLIENT_OLLAMA_MODEL exactly once")
    if signed_model_digest is not None:
        env_template, replacements = re.subn(
            r"^CLIENT_OLLAMA_MODEL_DIGEST=.*$",
            f"CLIENT_OLLAMA_MODEL_DIGEST={signed_model_digest}",
            env_template,
            flags=re.MULTILINE,
        )
        if replacements != 1:
            raise ValueError("Installer template must define CLIENT_OLLAMA_MODEL_DIGEST exactly once")

    # Reading only these fixed paths prevents caller-selected sources, archive
    # traversal names, local .env files or private signing tools from shipping.
    files = {
        "README.md": (directory / "INSTALL.md").read_bytes(),
        "docker-compose.client.yaml": (directory / "docker-compose.client.yaml").read_bytes(),
        "docker-compose.identity.yaml": (directory / "docker-compose.identity.yaml").read_bytes(),
        "docker-compose.recovery.yaml": (directory / "docker-compose.recovery.yaml").read_bytes(),
        "Caddyfile": (directory / "Caddyfile").read_bytes(),
        "validate_install.py": (directory / "validate_install.py").read_bytes(),
        "recovery.py": (directory / "recovery.py").read_bytes(),
        "compose_client.py": (directory / "compose_client.py").read_bytes(),
        "recovery_lock.py": (directory / "recovery_lock.py").read_bytes(),
        "enroll_identity.py": (directory / "enroll_identity.py").read_bytes(),
        ".env.example": env_template.encode("utf-8"),
        "client-release-manifest.json": manifest_bytes,
        "release-public-key.txt": (public_key + "\n").encode("ascii"),
    }
    files.update(third_party_files)
    if MODEL_IMAGE_KEYS <= set(images):
        files.update({
            "docker-compose.models.yaml": (directory / "docker-compose.models.yaml").read_bytes(),
            "warm_local_models.py": (directory / "warm_local_models.py").read_bytes(),
        })
    if private_key is not None:
        files.update({
            "update_agent.py": (directory / "update_agent.py").read_bytes(),
            "kodewaves-client-update.service": (directory / "kodewaves-client-update.service").read_bytes(),
            "kodewaves-client-update.timer": (directory / "kodewaves-client-update.timer").read_bytes(),
            "verify_installer.py": (directory / "verify_installer.py").read_bytes(),
        })
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
    archive_bytes = archive.getvalue()
    if len(archive_bytes) > MAX_INSTALLER_ARCHIVE_BYTES:
        raise ValueError(
            f"Installer archive exceeds supported size ({MAX_INSTALLER_ARCHIVE_BYTES} bytes)"
        )
    signature = (
        base64.urlsafe_b64encode(private_key.sign(archive_bytes)).rstrip(b"=") + b"\n"
        if private_key is not None else None
    )
    archive_created = False
    signature_created = False
    try:
        with output.open("xb") as destination:
            archive_created = True
            destination.write(archive_bytes)
        if signature is not None:
            with signature_output.open("xb") as destination:
                signature_created = True
                destination.write(signature)
    except Exception:
        if archive_created:
            output.unlink(missing_ok=True)
        if signature_created:
            signature_output.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images-env", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--release-public-key", required=True, type=Path)
    parser.add_argument("--release-private-key", required=True, type=Path,
                        help="Owner-only Ed25519 key that signed the release manifest")
    parser.add_argument(
        "--silo-source-archive", type=Path,
        help="Checksum-verified source archive matching the pinned PGSTY Silo image (defaults to deploy/client/third-party)",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    package_installer(
        args.images_env, args.manifest, args.release_public_key,
        args.release_private_key, args.output,
        silo_source_archive=args.silo_source_archive,
    )
    print(f"Customer installation archive written: {args.output.resolve()}")
    print(f"Detached archive signature written: {args.output.with_name(args.output.name + '.sig').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
