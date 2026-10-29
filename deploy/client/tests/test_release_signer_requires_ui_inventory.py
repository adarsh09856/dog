import json
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def test_release_signer_refuses_to_create_unpackageable_manifest_without_ui_inventory(tmp_path):
    root = Path(__file__).resolve().parents[3]
    key = Ed25519PrivateKey.generate()
    private_key = tmp_path / "release-private.key"
    private_key.write_bytes(key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    ))
    api_inventory = tmp_path / "api-inventory.json"
    api_inventory.write_text(json.dumps({"api/app.py": "a" * 64}), encoding="utf-8")
    manifest = tmp_path / "release-manifest.json"

    result = subprocess.run(
        [
            sys.executable,
            str(root / "owner-tools" / "sign_client_release.py"),
            "--files-json", str(api_inventory),
            "--private-key", str(private_key),
            "--output", str(manifest),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Protected UI file hash inventory is invalid" in result.stderr
    assert not manifest.exists()
