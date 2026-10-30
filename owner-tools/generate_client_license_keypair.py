#!/usr/bin/env python3
"""Create an Ed25519 keypair for the Kodewaves owner license issuer."""

from __future__ import annotations

import argparse
import base64
import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _write_private_key(path: Path, private_bytes: bytes, *, force: bool) -> None:
    """Create a private key without a permissive file mode or overwrite race."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not force:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "wb") as key_file:
            key_file.write(private_bytes)
        return

    # A replacement is published atomically so a running owner API cannot
    # read a truncated key while an operator intentionally rotates it.
    fd, temporary_path = tempfile.mkstemp(prefix=".owner-key-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as key_file:
            key_file.write(private_bytes)
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-key", required=True, type=Path, help="Owner-only private key file to create")
    parser.add_argument("--force", action="store_true", help="Replace an existing private key file")
    args = parser.parse_args()
    key = Ed25519PrivateKey.generate()
    private_bytes = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    try:
        _write_private_key(args.private_key, private_bytes, force=args.force)
    except FileExistsError:
        parser.error("private key file already exists; pass --force only for intentional key rotation")
    public_key = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode("ascii")
    print(f"Public key (safe for client installs): {public_key}")
    print(f"Private key saved on owner system: {args.private_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
