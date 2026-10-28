from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "deploy/client"))
import recovery  # noqa: E402


def _archive(path: Path, *, extra: tuple[str, bytes] | None = None, corrupt: str | None = None):
    def volume_snapshot(name: str) -> bytes:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as volume:
            item = tarfile.TarInfo("data/example")
            payload = (name + "-data").encode()
            item.size = len(payload)
            volume.addfile(item, io.BytesIO(payload))
        return buffer.getvalue()

    env = (
        b"KODEWAVES_INSTALLATION_ID=customer-123\n"
        b"CLIENT_IDENTITY_KEY_FILE=/secure/identity.key\n"
        b"CLIENT_IDENTITY_GID=1234\n"
        b"KODEWAVES_LICENSE_TOKEN=payload.signature\n"
        b"CLIENT_API_IMAGE=registry.example.com/kodewaves/api@sha256:"
        + b"a" * 64 + b"\nCLIENT_UI_IMAGE=registry.example.com/kodewaves/ui@sha256:"
        + b"b" * 64 + b"\n"
    )
    manifest_bytes = json.dumps({
        "payload": {
            "edition": "client",
            "images": {
                "api": {"reference": "registry.example.com/kodewaves/api@sha256:" + "a" * 64},
                "ui": {"reference": "registry.example.com/kodewaves/ui@sha256:" + "b" * 64},
            },
        },
    }).encode()
    metadata = {
        "format": "kodewaves-client-recovery-v1",
        "snapshot_mode": "cold",
        "writers_stopped": True,
        "redis_included": False,
        "installation_id": "customer-123",
        "license_sha256": hashlib.sha256(b"payload.signature").hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "api_image": "registry.example.com/kodewaves/api@sha256:" + "a" * 64,
        "ui_image": "registry.example.com/kodewaves/ui@sha256:" + "b" * 64,
        "identity_gid": 1234,
        "identity_uid": 0,
        "identity_mode": 0o640,
    }
    files = {
        "recovery.json": json.dumps({
            **metadata,
        }).encode(),
        "volumes/postgres.tar": volume_snapshot("postgres"),
        "volumes/minio.tar": volume_snapshot("minio"),
        "config/.env": env,
        "config/client-release-manifest.json": manifest_bytes,
        "config/release-public-key.txt": b"trusted-public-key\n",
        "config/installation.key": b"k" * 32,
    }
    if extra:
        files[extra[0]] = extra[1]
    checksums = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(files.items())
    ).encode()
    files["SHA256SUMS"] = checksums
    if corrupt:
        files[corrupt] += b"tampered"
    with tarfile.open(path, "w:gz") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o640 if name == "config/installation.key" else 0o600 if name == "config/.env" else 0o644
            if name == "config/installation.key":
                member.gid = 1234
                member.uid = 0
            archive.addfile(member, io.BytesIO(data))


def test_recovery_archive_validates_without_extracting(tmp_path):
    path = tmp_path / "backup.tar.gz"
    _archive(path)

    result = recovery.validate_archive(path)

    assert result == {
        "status": "validated",
        "installation_id": "customer-123",
        "contains_identity_key": True,
        "snapshot_mode": "cold",
        "restore_performed": False,
    }
    assert list(tmp_path.iterdir()) == [path]


def _create_archive_inputs(tmp_path: Path) -> dict[str, Path]:
    postgres = tmp_path / "postgres.tar"
    minio = tmp_path / "minio.tar"
    for path, name in ((postgres, "postgres"), (minio, "minio")):
        with tarfile.open(path, "w") as volume:
            payload = (name + "-cold-data").encode()
            member = tarfile.TarInfo("data/example")
            member.size = len(payload)
            volume.addfile(member, io.BytesIO(payload))
    _, files = _archive_contents_for_test()
    env = tmp_path / ".env"
    env.write_bytes(files["config/.env"])
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(files["config/client-release-manifest.json"])
    public_key = tmp_path / "release-public-key.txt"
    public_key.write_bytes(files["config/release-public-key.txt"])
    identity = tmp_path / "identity.key"
    identity.write_bytes(b"k" * 32)
    if os.name != "nt":
        os.chmod(identity, 0o640)
        try:
            os.chown(identity, os.getuid(), 1234)
        except PermissionError:
            pytest.skip("test needs permission to set the fixture identity GID")
    return {
        "postgres": postgres,
        "minio": minio,
        "env": env,
        "manifest": manifest,
        "public_key": public_key,
        "identity": identity,
    }


def _archive_contents_for_test() -> tuple[Path, dict[str, bytes]]:
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "source.tar.gz"
        _archive(path)
        with tarfile.open(path, "r:gz") as source:
            return path, {
                member.name: source.extractfile(member).read()
                for member in source.getmembers()
                if member.isfile()
            }


def test_create_and_stage_offline_recovery_archive(tmp_path):
    inputs = _create_archive_inputs(tmp_path)
    archive_path = tmp_path / "recovery.tar.gz"
    created = recovery.create_archive(
        postgres_tar=inputs["postgres"], minio_tar=inputs["minio"],
        env_file=inputs["env"], manifest=inputs["manifest"],
        release_public_key=inputs["public_key"], identity_key=inputs["identity"],
        output=archive_path, writers_stopped=True,
    )
    assert created["status"] == "created"
    assert recovery.validate_archive(archive_path)["installation_id"] == "customer-123"

    destination = tmp_path / "offline-restore"
    staged = recovery.restore_to_directory(archive_path, destination)
    assert staged["status"] == "staged"
    assert staged["docker_volumes_modified"] is False
    assert (destination / "volumes/postgres.tar").read_bytes() == inputs["postgres"].read_bytes()
    assert (destination / "volumes/minio.tar").read_bytes() == inputs["minio"].read_bytes()
    assert (destination / "config/.env").read_bytes() == inputs["env"].read_bytes()
    assert (destination / "config/installation.key").read_bytes() == b"k" * 32


def test_create_requires_maintenance_attestation_and_exclusive_destination(tmp_path):
    inputs = _create_archive_inputs(tmp_path)
    archive_path = tmp_path / "backup.tar.gz"
    kwargs = {
        "postgres_tar": inputs["postgres"], "minio_tar": inputs["minio"],
        "env_file": inputs["env"], "manifest": inputs["manifest"],
        "release_public_key": inputs["public_key"], "identity_key": inputs["identity"],
        "output": archive_path,
    }
    with pytest.raises(ValueError, match="stopped writers"):
        recovery.create_archive(**kwargs, writers_stopped=False)
    assert not archive_path.exists()
    recovery.create_archive(**kwargs, writers_stopped=True)
    archive_path.write_bytes(b"keep existing")
    with pytest.raises(ValueError, match="already exists"):
        recovery.create_archive(**kwargs, writers_stopped=True)
    assert archive_path.read_bytes() == b"keep existing"


def test_restore_refuses_existing_destination_without_touching_it(tmp_path):
    archive_path = tmp_path / "backup.tar.gz"
    _archive(archive_path)
    destination = tmp_path / "existing"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("keep")

    with pytest.raises(ValueError, match="already exists"):
        recovery.restore_to_directory(archive_path, destination)
    assert sentinel.read_text() == "keep"


@pytest.mark.parametrize("extra", [
    ("../escape", b"bad"),
    ("unexpected.txt", b"bad"),
])
def test_recovery_archive_rejects_unsafe_or_unexpected_members(tmp_path, extra):
    path = tmp_path / "bad.tar.gz"
    _archive(path, extra=extra)

    with pytest.raises(ValueError):
        recovery.validate_archive(path)


def test_recovery_archive_rejects_checksum_mismatch(tmp_path):
    path = tmp_path / "bad.tar.gz"
    _archive(path, corrupt="volumes/minio.tar")

    with pytest.raises(ValueError, match="Checksum mismatch"):
        recovery.validate_archive(path)


def test_recovery_archive_rejects_identity_key_with_wrong_permissions(tmp_path):
    path = tmp_path / "bad.tar.gz"
    _archive(path)
    replacement = tmp_path / "mode.tar.gz"
    with tarfile.open(path, "r:gz") as source, tarfile.open(replacement, "w:gz") as target:
        for member in source.getmembers():
            data = source.extractfile(member).read()
            if member.name == "config/installation.key":
                member.mode = 0o644
                member.gid = 1234
                member.uid = 0
            target.addfile(member, io.BytesIO(data))

    with pytest.raises(ValueError, match="0640 permissions"):
        recovery.validate_archive(replacement)


def test_recovery_archive_rejects_mismatched_installation_identity(tmp_path):
    path = tmp_path / "backup.tar.gz"
    _archive(path)
    replacement = tmp_path / "identity-mismatch.tar.gz"
    with tarfile.open(path, "r:gz") as source:
        entries = {member.name: source.extractfile(member).read() for member in source.getmembers()}
    entries["recovery.json"] = json.dumps({
        "format": "kodewaves-client-recovery-v1",
        "snapshot_mode": "cold",
        "writers_stopped": True,
        "redis_included": False,
        "installation_id": "different-123",
        "identity_gid": 1234,
        "identity_uid": 0,
        "identity_mode": 0o640,
    }).encode()
    entries["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(entries.items()) if name != "SHA256SUMS"
    ).encode()
    with tarfile.open(replacement, "w:gz") as target:
        for name, data in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o640 if name == "config/installation.key" else 0o600 if name == "config/.env" else 0o644
            if name == "config/installation.key":
                member.gid = 1234
                member.uid = 0
            target.addfile(member, io.BytesIO(data))
    with pytest.raises(ValueError, match="does not match the archived .env"):
        recovery.validate_archive(replacement)


def test_recovery_archive_rejects_non_cold_snapshot_declaration(tmp_path):
    path = tmp_path / "bad.tar.gz"
    _archive(path)
    replacement = tmp_path / "warm.tar.gz"
    with tarfile.open(path, "r:gz") as source:
        entries = {member.name: source.extractfile(member).read() for member in source.getmembers()}
    metadata = json.loads(entries["recovery.json"])
    metadata["snapshot_mode"] = "live"
    entries["recovery.json"] = json.dumps(metadata).encode()
    entries["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(entries.items()) if name != "SHA256SUMS"
    ).encode()
    with tarfile.open(replacement, "w:gz") as target:
        for name, data in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o640 if name == "config/installation.key" else 0o600 if name == "config/.env" else 0o644
            if name == "config/installation.key":
                member.gid = 1234
                member.uid = 0
            target.addfile(member, io.BytesIO(data))

    with pytest.raises(ValueError, match="cold snapshot"):
        recovery.validate_archive(replacement)


def test_recovery_archive_rejects_nested_path_traversal_and_links(tmp_path):
    def malicious_volume(name: str, *, link: bool) -> bytes:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as volume:
            member = tarfile.TarInfo("../outside" if not link else "inside-link")
            if link:
                member.type = tarfile.SYMTYPE
                member.linkname = "../../outside"
                volume.addfile(member)
            else:
                payload = b"bad"
                member.size = len(payload)
                volume.addfile(member, io.BytesIO(payload))
        return buffer.getvalue()

    for link in (False, True):
        path = tmp_path / f"nested-{link}.tar.gz"
        _archive(path)
        replacement = tmp_path / f"nested-bad-{link}.tar.gz"
        with tarfile.open(path, "r:gz") as source:
            entries = {member.name: source.extractfile(member).read() for member in source.getmembers()}
        entries["volumes/postgres.tar"] = malicious_volume("postgres", link=link)
        entries["SHA256SUMS"] = "".join(
            f"{hashlib.sha256(data).hexdigest()}  {name}\n"
            for name, data in sorted(entries.items()) if name != "SHA256SUMS"
        ).encode()
        with tarfile.open(replacement, "w:gz") as target:
            for name, data in entries.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                member.mode = 0o640 if name == "config/installation.key" else 0o600 if name == "config/.env" else 0o644
                if name == "config/installation.key":
                    member.gid = 1234
                target.addfile(member, io.BytesIO(data))
        with pytest.raises(ValueError):
            recovery.validate_archive(replacement)
