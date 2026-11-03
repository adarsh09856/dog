#!/usr/bin/env python3
"""Create an owner-signed metadata envelope for a client update archive."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "deploy/client"))

from api.services.client_update_protocol import canonical_json, release_signature_payload
from build_and_verify import read_public_key, validate_owner_private_key_path

MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_NOTES_CHARS = 4000
MAX_URL_CHARS = 2048


def _private_key_bytes(path: Path) -> bytes:
    if path.stat().st_size > 64:
        raise ValueError("Release private key file is oversized")
    raw = path.read_bytes()
    if len(raw) == 32:
        return raw
    try:
        encoded = raw.decode("ascii").strip()
        # The canonical unpadded representation is 43 characters; one
        # optional Base64 padding character is accepted for owner keys.
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}=?", encoded):
            raise ValueError("invalid encoding")
        decoded = base64.b64decode(
            encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True,
        )
        if (
            len(decoded) != 32
            or base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
            != encoded.rstrip("=")
        ):
            raise ValueError("non-canonical key")
        return decoded
    except (UnicodeDecodeError, ValueError, binascii.Error) as exc:
        raise ValueError(
            "Release private key must be 32 raw bytes or canonical URL-safe Base64"
        ) from exc


def _trusted_public_key_bytes(path: Path) -> bytes:
    if path.stat().st_size > 64:
        raise ValueError("Trusted release public key file is oversized")
    encoded = read_public_key(path)
    try:
        return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Trusted release public key is invalid") from exc


def _archive_sha256(path: Path) -> str:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError("Update archive must be an existing regular file") from exc
    if path.is_symlink() or not path.is_file() or metadata.st_size < 1:
        raise ValueError("Update archive must be a nonempty regular file, not a symlink")
    if metadata.st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Update archive exceeds the 2 GiB size limit")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_update_release_envelope(
    *,
    archive: Path,
    release_id: str,
    version: str,
    archive_url: str,
    min_current_version: str,
    notes: str,
    release_private_key: Path,
    trusted_public_key: Path,
    output: Path,
) -> dict[str, str]:
    """Validate inputs, sign canonical release metadata and create an exclusive JSON output."""
    if not isinstance(notes, str) or len(notes) > MAX_NOTES_CHARS:
        raise ValueError("Release notes must be at most 4000 characters")
    if not isinstance(archive_url, str) or len(archive_url) > MAX_URL_CHARS:
        raise ValueError("Archive URL must be at most 2048 characters")

    private_path = validate_owner_private_key_path(release_private_key, ROOT)
    payload = release_signature_payload(
        release_id=release_id,
        version=version,
        archive_url=archive_url,
        archive_sha256=_archive_sha256(archive),
        min_current_version=min_current_version,
        notes=notes,
    )

    private = Ed25519PrivateKey.from_private_bytes(_private_key_bytes(private_path))
    trusted_public_bytes = _trusted_public_key_bytes(trusted_public_key)
    derived_public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    if derived_public != trusted_public_bytes:
        raise ValueError("Release private key does not match the trusted public key")

    signature = base64.urlsafe_b64encode(private.sign(canonical_json(payload))).rstrip(b"=").decode("ascii")
    envelope = {**payload, "archive_signature": signature}
    serialized = json.dumps(envelope, indent=2, ensure_ascii=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with output.open("x", encoding="utf-8", newline="\n") as destination:
            created = True
            destination.write(serialized)
    except Exception:
        if created:
            output.unlink(missing_ok=True)
        raise
    return envelope


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--archive-url", required=True)
    parser.add_argument("--min-current-version", required=True)
    parser.add_argument("--notes", default="")
    parser.add_argument("--release-private-key", required=True, type=Path)
    parser.add_argument("--trusted-public-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        envelope = create_update_release_envelope(
            archive=args.archive,
            release_id=args.release_id,
            version=args.version,
            archive_url=args.archive_url,
            min_current_version=args.min_current_version,
            notes=args.notes,
            release_private_key=args.release_private_key,
            trusted_public_key=args.trusted_public_key,
            output=args.output,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        f"Signed release {envelope['release_id']} ({envelope['version']}); "
        f"archive SHA-256 {envelope['archive_sha256']}; envelope {args.output.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
