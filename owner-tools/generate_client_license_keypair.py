#!/usr/bin/env python3
"""Create an Ed25519 keypair for the Kodewaves owner license issuer."""

from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-key", required=True, type=Path, help="Owner-only private key file to create")
    parser.add_argument("--force", action="store_true", help="Replace an existing private key file")
    args = parser.parse_args()
    if args.private_key.exists() and not args.force:
        parser.error("private key file already exists; pass --force only for intentional key rotation")

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
    args.private_key.parent.mkdir(parents=True, exist_ok=True)
    args.private_key.write_bytes(private_bytes)
    try:
        os.chmod(args.private_key, 0o600)
    except OSError:
        pass
    public_key = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode("ascii")
    print(f"Public key (safe for client installs): {public_key}")
    print(f"Private key saved on owner system: {args.private_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
