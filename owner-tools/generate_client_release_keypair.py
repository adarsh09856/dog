#!/usr/bin/env python3
"""Create an owner Ed25519 release-signing keypair for client bundles.

Keep the private key on a trusted owner release machine, outside this source
checkout and every Docker build context. The public key can be supplied to the
client image builder and distributed with customer installers.
"""

from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _create_exclusive(path: Path, data: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, mode)
    try:
        with os.fdopen(descriptor, "wb") as key_file:
            key_file.write(data)
            key_file.flush()
            os.fsync(key_file.fileno())
    except OSError:
        path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-key", required=True, type=Path, help="Owner-only private key path outside the repository")
    parser.add_argument("--public-key", required=True, type=Path, help="Public verifier-key output path")
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    private_lexical = Path(os.path.abspath(args.private_key.expanduser()))
    private_parent = private_lexical.parent.resolve()
    private_target = private_parent / private_lexical.name
    if _is_within(private_lexical, repository_root) or _is_within(private_target, repository_root):
        parser.error("private key must be stored outside the repository and Docker build context")
    if private_target == args.public_key.expanduser().absolute():
        parser.error("private-key and public-key output paths must differ")

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
    public_text = base64.urlsafe_b64encode(public_bytes).rstrip(b"=") + b"\n"

    private_created = False
    try:
        _create_exclusive(private_target, private_bytes, mode=0o600)
        private_created = True
        _create_exclusive(args.public_key.expanduser(), public_text, mode=0o644)
    except FileExistsError:
        if private_created:
            private_target.unlink(missing_ok=True)
        parser.error("a key output already exists; choose new paths to avoid accidental key rotation")
    except OSError as exc:
        if private_created:
            private_target.unlink(missing_ok=True)
        parser.error(f"could not create keypair: {exc}")

    print(f"Private signing key saved on owner system: {private_target}")
    print(f"Public verification key saved: {args.public_key.expanduser().absolute()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
