#!/usr/bin/env python3
"""Issue a signed Kodewaves client-installation license from owner-only material.

Run from the Kodewaves owner repository and keep the Ed25519 private key on
that system. This tool is intentionally outside the API/UI Docker build
contexts so it is not included in client images.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.services.installation_license import (
    _b64url_decode,
    issue_license_token,
    load_license,
)


def _decode_key(value: str) -> bytes:
    return _b64url_decode(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", required=True, type=Path, help="JSON claims file")
    parser.add_argument("--private-key", required=True, type=Path, help="Owner-only raw or base64url Ed25519 private key")
    parser.add_argument("--public-key", required=True, help="Base64url Ed25519 public key for verification")
    parser.add_argument("--output", required=True, type=Path, help="Destination file for the signed license token")
    args = parser.parse_args()

    key_data = args.private_key.read_bytes()
    if len(key_data) != 32:
        key_data = _decode_key(key_data.strip().decode("ascii"))
    claims = json.loads(args.claims.read_text(encoding="utf-8"))
    token = issue_license_token(claims, key_data)
    load_license(token, args.public_key)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(token + "\n", encoding="ascii")
    try:
        os.chmod(args.output, 0o600)
    except OSError:
        pass
    print(f"Issued client license for installation {claims['installation_id']}; token saved to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
