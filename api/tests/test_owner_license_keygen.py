"""Owner license key creation must not leak or overwrite keys accidentally."""

import base64
import os
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


SCRIPT = Path(__file__).resolve().parents[2] / "owner-tools/generate_client_license_keypair.py"


def _run(path: Path, *args: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--private-key", str(path), *args],
        capture_output=True, text=True, check=False,
    )


def test_key_creation_is_exclusive_and_public_key_matches(tmp_path):
    path = tmp_path / "owner" / "current.key"
    path.parent.mkdir()
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: _run(path), range(2)))
    assert sorted(result.returncode for result in outcomes) == [0, 2]
    private = Ed25519PrivateKey.from_private_bytes(path.read_bytes())
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    encoded = base64.urlsafe_b64encode(public).rstrip(b"=").decode("ascii")
    winner = next(result for result in outcomes if result.returncode == 0)
    assert encoded in winner.stdout
    assert path.read_bytes().hex() not in winner.stdout
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_existing_key_remains_unchanged_unless_force_is_explicit(tmp_path):
    path = tmp_path / "current.key"
    original = b"x" * 32
    path.write_bytes(original)
    assert _run(path).returncode == 2
    assert path.read_bytes() == original
    result = _run(path, "--force")
    assert result.returncode == 0, result.stderr
    assert len(path.read_bytes()) == 32 and path.read_bytes() != original
    assert not list(tmp_path.glob(".owner-key-*"))
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
