from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "owner-tools"))

import sign_client_update_release as signer
from api.services import client_update_protocol as protocol


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _key_files(directory: Path, key: Ed25519PrivateKey | None = None) -> tuple[Path, Path, Ed25519PrivateKey]:
    key = key or Ed25519PrivateKey.generate()
    private_path = directory / "release-private.key"
    private_path.write_bytes(key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    ))
    public_path = directory / "release-public.key"
    public_path.write_text(_b64url(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )), encoding="ascii")
    return private_path, public_path, key


def _inputs(tmp_path: Path, **overrides):
    private, public, key = _key_files(tmp_path)
    archive = tmp_path / "client-2.4.1.tar.gz"
    archive.write_bytes(b"exact approved client update bytes\x00")
    output = tmp_path / "release-envelope.json"
    values = {
        "archive": archive,
        "release_id": "release-2.4.1",
        "version": "2.4.1",
        "archive_url": "https://updates.example.com/releases/client-2.4.1.tar.gz",
        "min_current_version": "2.3.0",
        "notes": "  Security fixes and reliability improvements  ",
        "release_private_key": private,
        "trusted_public_key": public,
        "output": output,
    }
    values.update(overrides)
    return values, key, output


def test_creates_exact_api_envelope_and_signs_archive_hash(tmp_path, monkeypatch):
    values, key, output = _inputs(tmp_path)
    envelope = signer.create_update_release_envelope(**values)

    assert set(envelope) == {
        "release_id", "version", "archive_url", "archive_sha256",
        "archive_signature", "min_current_version", "notes",
    }
    assert envelope["archive_sha256"] == hashlib.sha256(values["archive"].read_bytes()).hexdigest()
    assert envelope["notes"] == "Security fixes and reliability improvements"
    assert json.loads(output.read_text(encoding="utf-8")) == envelope
    assert _b64url(key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )) not in output.read_text(encoding="utf-8")

    monkeypatch.setattr(protocol, "trusted_release_public_key", lambda: _b64url(
        key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ))
    assert protocol.verify_release_envelope(envelope) == envelope
    signed_payload = protocol.release_signature_payload(**{
        name: envelope[name]
        for name in ("release_id", "version", "archive_url", "archive_sha256", "min_current_version", "notes")
    })
    key.public_key().verify(
        base64.urlsafe_b64decode(envelope["archive_signature"] + "=="),
        protocol.canonical_json(signed_payload),
    )


@pytest.mark.parametrize(("field", "value", "message"), [
    ("release_id", "release id", "Release ID is invalid"),
    ("version", "2.4", "canonical X.Y.Z"),
    ("min_current_version", "2.5.0", "cannot exceed"),
    ("archive_url", "http://updates.example.com/archive.tgz", "valid HTTPS URL"),
    ("notes", "x" * 4001, "at most 4000"),
    ("archive_url", "https://updates.example.com/" + "x" * 2040, "2048 characters"),
])
def test_rejects_invalid_or_oversized_metadata(tmp_path, field, value, message):
    values, _, output = _inputs(tmp_path, **{field: value})
    with pytest.raises(ValueError, match=message):
        signer.create_update_release_envelope(**values)
    assert not output.exists()


def test_rejects_oversized_archive_before_hashing(tmp_path, monkeypatch):
    values, _, output = _inputs(tmp_path)
    monkeypatch.setattr(signer, "MAX_ARCHIVE_BYTES", 8)
    with pytest.raises(ValueError, match="2 GiB size limit"):
        signer.create_update_release_envelope(**values)
    assert not output.exists()


def test_requires_matching_external_public_key_and_never_overwrites(tmp_path):
    values, _, output = _inputs(tmp_path)
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    _other_private, other_public, _other_key = _key_files(other_dir)
    values["trusted_public_key"] = other_public
    with pytest.raises(ValueError, match="does not match the trusted public key"):
        signer.create_update_release_envelope(**values)
    assert not output.exists()

    values, _, output = _inputs(tmp_path)
    output.write_text("preserve existing output", encoding="utf-8")
    with pytest.raises(FileExistsError):
        signer.create_update_release_envelope(**values)
    assert output.read_text(encoding="utf-8") == "preserve existing output"


def test_rejects_missing_archive_and_bad_key_material(tmp_path):
    values, _, output = _inputs(tmp_path)
    missing = tmp_path / "missing.tar.gz"
    values["archive"] = missing
    with pytest.raises(ValueError, match="existing regular file"):
        signer.create_update_release_envelope(**values)
    assert not output.exists()

    values, _, output = _inputs(tmp_path)
    bad_key = tmp_path / "bad-private.key"
    bad_key.write_bytes(b"x" * 31)
    values["release_private_key"] = bad_key
    with pytest.raises(ValueError, match="private key must be 32 raw bytes"):
        signer.create_update_release_envelope(**values)
    assert not output.exists()


def test_rejects_private_key_path_inside_repository(tmp_path):
    values, _, output = _inputs(tmp_path)
    values["release_private_key"] = ROOT / "owner-tools" / "sign_client_update_release.py"
    with pytest.raises(ValueError, match="outside the repository/build context"):
        signer.create_update_release_envelope(**values)
    assert not output.exists()
