#!/usr/bin/env python3
"""Verify a customer installer archive before extracting or running its contents."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import re
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def _read_trusted_public_key(path: Path) -> bytes:
    """Read a canonical Ed25519 public key supplied outside the archive."""
    try:
        encoded = path.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}=?", encoded):
            raise ValueError("expected canonical URL-safe Base64")
        key = base64.b64decode(
            encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True,
        )
        if (
            len(key) != 32
            or base64.urlsafe_b64encode(key).rstrip(b"=").decode("ascii")
            != encoded.rstrip("=")
        ):
            raise ValueError("non-canonical Ed25519 key")
        Ed25519PublicKey.from_public_bytes(key)
        return key
    except (OSError, UnicodeDecodeError, ValueError, binascii.Error) as exc:
        raise ValueError(f"Invalid trusted release public key file: {path}") from exc


def verify_installer_archive(
    archive: Path,
    signature_file: Path,
    trusted_public_key_file: Path,
) -> str:
    """Verify exact archive bytes using a key supplied independently of the archive."""
    try:
        archive_bytes = archive.read_bytes()
        encoded_signature = signature_file.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{86}", encoded_signature):
            raise ValueError("signature is not canonical URL-safe Base64")
        signature = base64.urlsafe_b64decode(encoded_signature + "==")
        if (
            len(signature) != 64
            or base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
            != encoded_signature
        ):
            raise ValueError("signature is not canonical URL-safe Base64")
        key = Ed25519PublicKey.from_public_bytes(
            _read_trusted_public_key(trusted_public_key_file)
        )
        key.verify(signature, archive_bytes)
    except InvalidSignature as exc:
        raise ValueError("Customer installer archive signature is invalid") from exc
    except (OSError, UnicodeDecodeError, ValueError, binascii.Error) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("Invalid trusted release public key"):
            raise
        raise ValueError(f"Unable to verify customer installer archive: {exc}") from exc
    return hashlib.sha256(archive_bytes).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument(
        "--signature", type=Path,
        help="Detached signature file; defaults to <archive>.sig",
    )
    parser.add_argument(
        "--trusted-public-key", required=True, type=Path,
        help="Trusted Ed25519 release key obtained independently of the archive",
    )
    args = parser.parse_args()
    signature = args.signature or args.archive.with_name(args.archive.name + ".sig")
    digest = verify_installer_archive(args.archive, signature, args.trusted_public_key)
    print(f"Installer signature verified; SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
