from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ci_verify import _configure_customer_install, _extract_customer_archive


def _archive(path: Path, files: dict[str, bytes]) -> None:
    checksums = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(files.items())
    ).encode("ascii")
    files = {**files, "SHA256SUMS": checksums}
    with tarfile.open(path, "w:gz") as bundle:
        for name, content in sorted(files.items()):
            item = tarfile.TarInfo(name)
            item.size = len(content)
            item.mode = 0o644
            bundle.addfile(item, io.BytesIO(content))


def test_extracted_installer_checks_every_file(tmp_path: Path) -> None:
    archive = tmp_path / "customer.tar.gz"
    _archive(archive, {"README.md": b"install", "client-release-manifest.json": b"signed"})

    extracted = _extract_customer_archive(archive, tmp_path / "unpacked")

    assert (extracted / "README.md").read_bytes() == b"install"
    assert (extracted / "client-release-manifest.json").read_bytes() == b"signed"


def test_extraction_rejects_checksum_mismatch(tmp_path: Path) -> None:
    archive = tmp_path / "customer.tar.gz"
    _archive(archive, {"README.md": b"install"})
    # Rebuild a structurally valid archive whose recorded digest no longer
    # matches its file, as would happen after an accidental package mutation.
    bad_archive = tmp_path / "tampered.tar.gz"
    with tarfile.open(archive, "r:gz") as source:
        entries = {member.name: source.extractfile(member).read() for member in source.getmembers()}
    entries["README.md"] = b"changed"
    with tarfile.open(bad_archive, "w:gz") as bundle:
        for name, content in sorted(entries.items()):
            item = tarfile.TarInfo(name)
            item.size = len(content)
            item.mode = 0o644
            bundle.addfile(item, io.BytesIO(content))

    with pytest.raises(ValueError, match="checksum failed: README.md"):
        _extract_customer_archive(bad_archive, tmp_path / "tampered")


@pytest.mark.parametrize(
    "name,member_type,linkname",
    [
        ("../outside.txt", tarfile.REGTYPE, ""),
        ("linked.txt", tarfile.SYMTYPE, "../outside.txt"),
    ],
)
def test_extraction_rejects_unsafe_entries(
    tmp_path: Path, name: str, member_type: bytes, linkname: str
) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        member = tarfile.TarInfo(name)
        member.type = member_type
        member.linkname = linkname
        member.size = 0
        bundle.addfile(member)

    with pytest.raises(ValueError, match="unsafe entry"):
        _extract_customer_archive(archive, tmp_path / "unsafe")


def test_extraction_rejects_duplicate_names(tmp_path: Path) -> None:
    archive = tmp_path / "duplicate.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for content in (b"first", b"second"):
            member = tarfile.TarInfo("README.md")
            member.size = len(content)
            bundle.addfile(member, io.BytesIO(content))

    with pytest.raises(ValueError, match="duplicate or missing entries"):
        _extract_customer_archive(archive, tmp_path / "duplicate")


def test_customer_env_uses_pinned_digest_images_and_fresh_identity_path(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1]
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    (install_dir / ".env.example").write_bytes((source / ".env.example").read_bytes())
    (install_dir / "docker-compose.client.yaml").write_bytes(
        (source / "docker-compose.client.yaml").read_bytes()
    )
    refs = {
        "api": "localhost:5000/kodewaves-ci/client-api@sha256:" + "a" * 64,
        "ui": "localhost:5000/kodewaves-ci/client-ui@sha256:" + "b" * 64,
        "minio": "localhost:5000/kodewaves-ci/minio@sha256:" + "c" * 64,
    }
    key_file = tmp_path / "identity.key"

    env_path = _configure_customer_install(
        install_dir,
        license_token="ci-payload.signature",
        key_file=key_file,
        api_image=refs["api"],
        ui_image=refs["ui"],
        minio_image=refs["minio"],
        caddy_image="docker.io/library/caddy@sha256:" + "d" * 64,
        project="kw-ci-install-test",
    )

    values = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    assert values["CLIENT_API_IMAGE"] == refs["api"]
    assert values["CLIENT_UI_IMAGE"] == refs["ui"]
    assert values["CLIENT_MINIO_IMAGE"] == refs["minio"]
    assert values["CLIENT_RELEASE_MANIFEST_FILE"] == str(
        (install_dir / "client-release-manifest.json").resolve()
    )
    assert values["CLIENT_IDENTITY_KEY_FILE"] == str(key_file.resolve())
    assert values["COMPOSE_PROFILES"] == ""
