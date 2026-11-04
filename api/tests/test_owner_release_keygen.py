"""Client release signing keys must be owner-only and never overwritten."""

import base64
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


SCRIPT = Path(__file__).resolve().parents[2] / "owner-tools/generate_client_release_keypair.py"
SIGNER = SCRIPT.with_name("sign_client_release.py")
REPOSITORY = SCRIPT.parents[1]


def _run(private_path: Path, public_path: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--private-key", str(private_path), "--public-key", str(public_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_release_keypair_is_matching_and_private_key_is_owner_only(tmp_path):
    private_path = tmp_path / "secure" / "release-private.key"
    public_path = tmp_path / "release-public.key"

    result = _run(private_path, public_path)

    assert result.returncode == 0, result.stderr
    private_bytes = private_path.read_bytes()
    assert len(private_bytes) == 32
    private = Ed25519PrivateKey.from_private_bytes(private_bytes)
    expected_public = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    encoded_public = base64.urlsafe_b64encode(expected_public).rstrip(b"=") + b"\n"
    assert public_path.read_bytes() == encoded_public
    assert private_bytes.hex() not in result.stdout
    api_inventory = tmp_path / "api-inventory.json"
    ui_inventory = tmp_path / "ui-inventory.json"
    manifest_path = tmp_path / "release-manifest.json"
    api_inventory.write_text(json.dumps({"api/main.py": "a" * 64}), encoding="utf-8")
    ui_inventory.write_text(json.dumps({"ui/server.js": "b" * 64}), encoding="utf-8")
    signed = subprocess.run(
        [
            sys.executable, str(SIGNER), "--files-json", str(api_inventory),
            "--ui-files-json", str(ui_inventory), "--private-key", str(private_path),
            "--public-key-output", str(tmp_path / "signer-public.key"),
            "--output", str(manifest_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert signed.returncode == 0, signed.stderr
    signed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    canonical_payload = json.dumps(signed_manifest["payload"], sort_keys=True, separators=(",", ":")).encode()
    Ed25519PrivateKey.from_private_bytes(private_bytes).public_key().verify(
        base64.urlsafe_b64decode(signed_manifest["signature"] + "=" * (-len(signed_manifest["signature"]) % 4)),
        canonical_payload,
    )
    if os.name != "nt":
        assert stat.S_IMODE(private_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(public_path.stat().st_mode) == 0o644


def test_existing_output_refuses_overwrite_and_keeps_existing_key(tmp_path):
    private_path = tmp_path / "release-private.key"
    public_path = tmp_path / "release-public.key"
    public_path.write_text("existing public key\n", encoding="ascii")

    result = _run(private_path, public_path)

    assert result.returncode == 2
    assert not private_path.exists()
    assert public_path.read_text(encoding="ascii") == "existing public key\n"


def test_private_key_path_inside_repository_is_rejected(tmp_path):
    private_path = REPOSITORY / ".release-key-test-never-create.key"
    public_path = tmp_path / "release-public.key"

    result = _run(private_path, public_path)

    assert result.returncode == 2
    assert "outside the repository" in result.stderr
    assert not private_path.exists()
    assert not public_path.exists()
