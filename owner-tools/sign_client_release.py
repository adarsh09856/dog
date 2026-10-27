#!/usr/bin/env python3
"""Sign protected client image contents without placing the owner key in the image."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.services.release_integrity import protected_files, verify_release_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--root", type=Path, help="Source root matching the client image")
    source.add_argument("--files-json", type=Path, help="Protected-file hashes read from the built client image")
    parser.add_argument("--ui-files-json", type=Path, help="Protected UI hashes read from the built client image")
    parser.add_argument("--images-json", type=Path, help="API/UI immutable image references and kinds")
    parser.add_argument("--schema-compatibility-json", type=Path, help="Alembic compatibility metadata")
    parser.add_argument("--private-key", type=Path, required=True, help="Owner-only Ed25519 key file")
    parser.add_argument("--output", type=Path, required=True, help="Signed manifest destination")
    parser.add_argument("--public-key-output", type=Path, help="Optional release verification key destination")
    args = parser.parse_args()

    key_data = args.private_key.read_bytes()
    if len(key_data) != 32:
        try:
            encoded_key = key_data.decode("ascii").strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{43}=?", encoded_key):
                raise ValueError("invalid encoding")
            key_data = base64.b64decode(
                encoded_key + "=" * (-len(encoded_key) % 4),
                altchars=b"-_", validate=True,
            )
            if (
                len(key_data) != 32
                or base64.urlsafe_b64encode(key_data).rstrip(b"=").decode("ascii")
                != encoded_key.rstrip("=")
            ):
                raise ValueError("non-canonical key")
        except (UnicodeDecodeError, ValueError, binascii.Error):
            parser.error("Owner private key must be 32 raw bytes or canonical URL-safe Base64")
    key = Ed25519PrivateKey.from_private_bytes(key_data)
    files = protected_files(args.root.resolve()) if args.root else json.loads(args.files_json.read_text(encoding="utf-8"))
    if not isinstance(files, dict) or not files or not all(
        isinstance(path, str) and isinstance(digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", digest)
        for path, digest in files.items()
    ):
        parser.error("Protected-file hash inventory is invalid")
    ui_files = json.loads(args.ui_files_json.read_text(encoding="utf-8")) if args.ui_files_json else {}
    if not isinstance(ui_files, dict) or not all(
        isinstance(path, str) and isinstance(digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", digest)
        for path, digest in ui_files.items()
    ):
        parser.error("Protected UI file hash inventory is invalid")
    if bool(args.images_json) != bool(args.schema_compatibility_json):
        parser.error("--images-json and --schema-compatibility-json must be used together")
    payload = {"edition": "client", "files": files, "ui_files": ui_files}
    if args.images_json:
        payload["images"] = json.loads(args.images_json.read_text(encoding="utf-8"))
        payload["schema_compatibility"] = json.loads(
            args.schema_compatibility_json.read_text(encoding="utf-8")
        )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = base64.urlsafe_b64encode(key.sign(canonical)).rstrip(b"=").decode("ascii")
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_key = base64.urlsafe_b64encode(public).rstrip(b"=").decode("ascii")
    args.output.write_text(json.dumps({"payload": payload, "signature": signature}, indent=2) + "\n", encoding="utf-8")
    if args.public_key_output:
        args.public_key_output.write_text(public_key + "\n", encoding="ascii")
    if args.root:
        verify_release_manifest(args.root.resolve(), args.output, public_key)
    print(f"Signed {len(payload['files'])} protected files; public key: {public_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
