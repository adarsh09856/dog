from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "deploy/client"))
import update_agent


def _valid_update() -> dict:
    return {
        "release_id": "release-1",
        "version": "1.3.0",
        "archive_url": "https://releases.example/client.tar.gz",
        "archive_sha256": "a" * 64,
        "archive_signature": "A" * 86,
        "min_current_version": "1.2.0",
        "notes": "approved release",
        "rollout_id": "13dbb634-9dc2-4a59-a3d8-44ff5c03a1c2",
        "target_status": "applying",
        "rollout_state": "active",
    }


def _env(directory: Path) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    identity = directory / "identity.key"
    identity.write_bytes(b"i" * 32)
    (directory / "release-public-key.txt").write_text("A" * 43, encoding="ascii")
    values = {
        "CLIENT_API_IMAGE": "registry.example/api@sha256:" + "a" * 64,
        "CLIENT_UI_IMAGE": "registry.example/ui@sha256:" + "b" * 64,
        "CLIENT_RELEASE_MANIFEST_FILE": "./client-release-1.2.0.json",
        "KODEWAVES_LICENSE_TOKEN": "license.payload",
        "KODEWAVES_INSTALLATION_ID": "client-1",
        "PUBLIC_HOST": "client.example",
        "CLIENT_IDENTITY_KEY_FILE": str(identity),
        "CLIENT_IDENTITY_GID": "10003",
    }
    (directory / ".env").write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    (directory / "client-release-1.2.0.json").write_text("{}", encoding="utf-8")
    for name in ("docker-compose.client.yaml", "docker-compose.identity.yaml", "docker-compose.recovery.yaml"):
        (directory / name).write_text("services: {}\n", encoding="utf-8")
    return values


def _fake_owner_status(monkeypatch, update: dict) -> list[dict]:
    calls: list[dict] = []

    def status(_env, _version):
        calls.append({"check": True})
        return ({"update": dict(update)}, "https://owner.example/api/v1/admin/client-installations/update-status")

    monkeypatch.setattr(update_agent, "_owner_status", status)
    return calls


def test_status_endpoint_accepts_only_pinned_owner_check_path():
    assert update_agent._status_endpoint(
        "https://owner.example/api/v1/admin/client-installations/check"
    ) == "https://owner.example/api/v1/admin/client-installations/update-status"
    for url in (
        "http://owner.example/api/v1/admin/client-installations/check",
        "https://owner.example/redirect?next=/client-installations/check",
        "https://user@owner.example/api/v1/admin/client-installations/check",
    ):
        with pytest.raises(update_agent.UpdateError):
            update_agent._status_endpoint(url)


def test_rollback_report_includes_restored_installed_version(monkeypatch):
    calls = {}
    monkeypatch.setattr(update_agent, "_read_identity_key", lambda *_args: b"i" * 32)
    monkeypatch.setattr(update_agent, "_current_version", lambda image: "1.2.0")
    def helper_request(_image, request):
        calls["signed"] = request
        return {"proof_signature": "p" * 86}

    monkeypatch.setattr(update_agent, "_helper_request", helper_request)
    monkeypatch.setattr(
        update_agent,
        "_owner_post",
        lambda url, token, body: calls.update({"url": url, "token": token, "body": body}),
    )
    env = {
        "CLIENT_API_IMAGE": "registry.example/api@sha256:" + "a" * 64,
        "CLIENT_IDENTITY_KEY_FILE": "identity.key",
        "CLIENT_IDENTITY_GID": "10003",
        "KODEWAVES_LICENSE_TOKEN": "license.payload",
        "KODEWAVES_INSTALLATION_ID": "client-1",
        "PUBLIC_HOST": "client.example",
    }
    update = {
        "rollout_id": "13dbb634-9dc2-4a59-a3d8-44ff5c03a1c2",
        "release_id": "release-1",
        "version": "1.3.0",
    }

    update_agent._report(env, "https://owner.example/update-status", update, "rolled_back")

    assert calls["signed"]["installed_version"] == "1.2.0"
    assert calls["body"]["installed_version"] == "1.2.0"


def test_archive_extractor_requires_exact_safe_checksum_covered_files(tmp_path: Path):
    contents = {name: b"fixture" for name in update_agent._PACKAGE_FILES if name != "SHA256SUMS"}
    contents["client-release-manifest.json"] = json.dumps({"payload": {"edition": "client"}}).encode()
    checksums = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(contents.items())
    ).encode()
    contents["SHA256SUMS"] = checksums
    archive_path = tmp_path / "bundle.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for name, data in contents.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    destination = tmp_path / "extracted"
    parsed = update_agent._extract_verified_archive(archive_path, destination)
    assert parsed["payload"]["edition"] == "client"
    assert set(item.name for item in destination.iterdir()) == update_agent._PACKAGE_FILES


def test_archive_extractor_rejects_path_traversal_before_writing(tmp_path: Path):
    archive_path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo("../outside")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))
    destination = tmp_path / "extracted"
    with pytest.raises(update_agent.UpdateError, match="unsafe entry"):
        update_agent._extract_verified_archive(archive_path, destination)
    assert not (tmp_path / "outside").exists()
    assert not destination.exists()


def test_manifest_install_is_atomic_and_retry_safe_after_link_failure(tmp_path: Path, monkeypatch):
    manifest_path = tmp_path / "client-release-1.3.0-abc123.json"
    signed_bytes = b'{"payload":{"edition":"client"},"signature":"signed"}'
    original_link = update_agent.os.link

    def fail_before_final_link(_source, _destination):
        raise OSError("simulated interruption before atomic publish")

    monkeypatch.setattr(update_agent.os, "link", fail_before_final_link)
    with pytest.raises(update_agent.UpdateError, match="manifest could not be installed atomically"):
        update_agent._install_manifest_atomically(tmp_path, manifest_path, signed_bytes)

    assert not manifest_path.exists()
    assert not list(tmp_path.glob(f".{manifest_path.name}.*.tmp"))

    monkeypatch.setattr(update_agent.os, "link", original_link)
    update_agent._install_manifest_atomically(tmp_path, manifest_path, signed_bytes)
    update_agent._install_manifest_atomically(tmp_path, manifest_path, signed_bytes)
    assert manifest_path.read_bytes() == signed_bytes
    assert not list(tmp_path.glob(f".{manifest_path.name}.*.tmp"))


def test_manifest_requires_client_edition_and_digest_pinned_images():
    manifest = {"payload": {
        "edition": "client",
        "images": {
            "api": {"kind": "registry_digest", "reference": "registry.example/api@sha256:" + "a" * 64},
            "ui": {"kind": "registry_digest", "reference": "registry.example/ui@sha256:" + "b" * 64},
        },
        "schema_compatibility": {"head": "new", "rollback_to": ["old"]},
    }}
    refs, schema = update_agent._manifest_images(manifest)
    assert refs["api"].endswith("a" * 64)
    assert schema["head"] == "new"
    manifest["payload"]["edition"] = "hosted"
    with pytest.raises(update_agent.UpdateError):
        update_agent._manifest_images(manifest)


def test_same_version_interrupted_update_rolls_back_when_stack_is_unhealthy(tmp_path, monkeypatch):
    values = _env(tmp_path)
    update = _valid_update()
    _fake_owner_status(monkeypatch, update)
    monkeypatch.setattr(update_agent, "_current_version", lambda _image: "1.3.0")
    monkeypatch.setattr(update_agent, "_active_manifest", lambda *_args: {"schema": {"head": "candidate"}})
    monkeypatch.setattr(update_agent, "_wait_for_release_healthy", lambda *_args, **_kwargs: False)
    backup = tmp_path / ".client-update-work" / f"{update['release_id']}-{update['rollout_id']}" / "pre-update-recovery.tar.gz"
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b"verified-backup-fixture")
    rolled_back = []
    reports = []
    monkeypatch.setattr(update_agent.recovery, "_restore_to_docker_volumes_locked", lambda **kwargs: rolled_back.append(kwargs))
    monkeypatch.setattr(update_agent, "_report", lambda _env, _url, _update, state, detail="": reports.append((state, detail)))

    result = update_agent.update_once(tmp_path)

    assert "restored" in result
    assert rolled_back and rolled_back[0]["allow_release_rollback"] is True
    assert reports == [("rolled_back", "Health check failed after interrupted update")]


def test_same_version_unhealthy_resume_without_backup_never_reports_applied(tmp_path, monkeypatch):
    _env(tmp_path)
    update = _valid_update()
    _fake_owner_status(monkeypatch, update)
    monkeypatch.setattr(update_agent, "_current_version", lambda _image: "1.3.0")
    monkeypatch.setattr(update_agent, "_active_manifest", lambda *_args: {"schema": {"head": "candidate"}})
    monkeypatch.setattr(update_agent, "_wait_for_release_healthy", lambda *_args, **_kwargs: False)
    reports = []
    monkeypatch.setattr(update_agent, "_report", lambda *args: reports.append(args))

    with pytest.raises(update_agent.UpdateError, match="no trusted rollback archive"):
        update_agent.update_once(tmp_path)
    assert reports == []


def test_check_mode_does_not_download_or_report(tmp_path, monkeypatch):
    _env(tmp_path)
    update = _valid_update()
    update["target_status"] = "staged"
    _fake_owner_status(monkeypatch, update)
    monkeypatch.setattr(update_agent, "_current_version", lambda _image: "1.2.0")
    monkeypatch.setattr(update_agent, "_download", lambda *_args: pytest.fail("check mode downloaded an archive"))
    monkeypatch.setattr(update_agent, "_report", lambda *_args: pytest.fail("check mode reported an update"))

    result = update_agent.update_once(tmp_path, dry_run=True)

    assert "is ready" in result
    assert not (tmp_path / ".client-update-work").exists()


def _host_update_fixture(tmp_path: Path):
    install = tmp_path / "install"
    install.mkdir()
    extracted = tmp_path / "verified-archive"
    extracted.mkdir()
    systemd_dir = tmp_path / "systemd"
    systemd_dir.mkdir()
    work_dir = install / ".client-update-work" / "release-1"
    work_dir.mkdir(parents=True)
    for name in update_agent.HOST_TOOL_FILES:
        (install / name).write_bytes(f"old:{name}".encode())
        (extracted / name).write_bytes(f"new:{name}".encode())
    for name in update_agent.SYSTEMD_UNIT_FILES:
        (systemd_dir / name).write_bytes(f"old:{name}".encode())
        (extracted / name).write_bytes(f"new:{name}".encode())
    return install, extracted, work_dir, systemd_dir


def test_host_maintenance_updates_only_allowlisted_files_atomically(tmp_path: Path, monkeypatch):
    install, extracted, work_dir, systemd_dir = _host_update_fixture(tmp_path)
    reloads = []
    monkeypatch.setattr(update_agent, "_systemd_daemon_reload", lambda: reloads.append(True))

    update_agent._apply_host_maintenance(install, extracted, work_dir, systemd_dir=systemd_dir)

    assert all((install / name).read_bytes() == f"new:{name}".encode() for name in update_agent.HOST_TOOL_FILES)
    assert all((systemd_dir / name).read_bytes() == f"new:{name}".encode() for name in update_agent.SYSTEMD_UNIT_FILES)
    assert reloads == [True]
    journal = json.loads((work_dir / update_agent.HOST_JOURNAL_NAME).read_text(encoding="utf-8"))
    assert journal["state"] == "committed"
    assert not list(install.glob(".*.tmp"))
    assert not list(systemd_dir.glob(".*.tmp"))


def test_host_maintenance_rolls_back_files_if_daemon_reload_fails(tmp_path: Path, monkeypatch):
    install, extracted, work_dir, systemd_dir = _host_update_fixture(tmp_path)
    reloads = 0

    def fail_once():
        nonlocal reloads
        reloads += 1
        if reloads == 1:
            raise update_agent.UpdateError("injected daemon reload failure")

    monkeypatch.setattr(update_agent, "_systemd_daemon_reload", fail_once)
    with pytest.raises(update_agent.UpdateError, match="injected daemon reload failure"):
        update_agent._apply_host_maintenance(install, extracted, work_dir, systemd_dir=systemd_dir)

    assert all((install / name).read_bytes() == f"old:{name}".encode() for name in update_agent.HOST_TOOL_FILES)
    assert all((systemd_dir / name).read_bytes() == f"old:{name}".encode() for name in update_agent.SYSTEMD_UNIT_FILES)
    assert reloads == 2
    assert not (work_dir / update_agent.HOST_JOURNAL_NAME).exists()


def test_host_maintenance_reports_one_time_migration_when_unit_directory_is_not_writable(tmp_path: Path, monkeypatch):
    install, extracted, work_dir, systemd_dir = _host_update_fixture(tmp_path)
    original_mkstemp = update_agent.tempfile.mkstemp

    def denied_mkstemp(*args, **kwargs):
        if Path(kwargs.get("dir", "")) == systemd_dir:
            raise PermissionError("systemd sandbox denied write")
        return original_mkstemp(*args, **kwargs)

    monkeypatch.setattr(update_agent.tempfile, "mkstemp", denied_mkstemp)
    with pytest.raises(update_agent.ManualUnitMigrationRequired, match="One-time manual migration required"):
        update_agent._apply_host_maintenance(install, extracted, work_dir, systemd_dir=systemd_dir)

    assert all((install / name).read_bytes() == f"old:{name}".encode() for name in update_agent.HOST_TOOL_FILES)
    assert all((systemd_dir / name).read_bytes() == f"old:{name}".encode() for name in update_agent.SYSTEMD_UNIT_FILES)
    assert not (work_dir / update_agent.HOST_JOURNAL_NAME).exists()


@pytest.mark.parametrize("rollout_state", ["paused", "stopped"])
def test_terminal_rollout_never_activates_old_application_and_reports_failure(tmp_path: Path, monkeypatch, rollout_state: str):
    _env(tmp_path)
    update = _valid_update()
    update["rollout_state"] = rollout_state
    _fake_owner_status(monkeypatch, update)
    monkeypatch.setattr(update_agent, "_current_version", lambda _image: "1.2.0")
    monkeypatch.setattr(update_agent, "_download", lambda *_args: pytest.fail("terminal rollout downloaded an archive"))
    reports = []
    monkeypatch.setattr(update_agent, "_report", lambda _env, _url, _update, state, detail="": reports.append((state, detail)))

    result = update_agent.update_once(tmp_path)

    assert "activation was skipped" in result
    assert reports == [("failed", f"Owner {rollout_state} the rollout before this client activated it")]
    assert not (tmp_path / ".client-update-work").exists()


@pytest.mark.parametrize("rollout_state", ["paused", "stopped"])
def test_terminal_rollout_with_healthy_new_app_finishes_host_maintenance(tmp_path: Path, monkeypatch, rollout_state: str):
    values = _env(tmp_path)
    update = _valid_update()
    update["rollout_state"] = rollout_state
    _fake_owner_status(monkeypatch, update)
    monkeypatch.setattr(update_agent, "_current_version", lambda _image: "1.3.0")
    monkeypatch.setattr(update_agent, "_active_manifest", lambda *_args: {"schema": {"head": "candidate"}})
    monkeypatch.setattr(update_agent, "_wait_for_release_healthy", lambda *_args, **_kwargs: True)
    systemd_dir = tmp_path / "systemd"
    systemd_dir.mkdir()
    monkeypatch.setattr(update_agent, "SYSTEMD_UNIT_DIR", systemd_dir)
    work_dir = tmp_path / ".client-update-work" / f"{update['release_id']}-{update['rollout_id']}"
    extracted = work_dir / "unpacked"
    archive_path = work_dir / "release.tar.gz"

    def verified_archive(_update, current_work_dir, _public_key):
        current_work_dir.mkdir(parents=True, exist_ok=True)
        archive_path.write_bytes(b"verified")
        extracted.mkdir()
        return archive_path, extracted, {"verified": True}

    monkeypatch.setattr(update_agent, "_download_verified_host_release", verified_archive)
    monkeypatch.setattr(update_agent, "_manifest_images", lambda _manifest: (
        {"api": values["CLIENT_API_IMAGE"], "ui": values["CLIENT_UI_IMAGE"]},
        {"head": "candidate", "rollback_to": ["old"]},
    ))
    maintenance = []
    monkeypatch.setattr(update_agent, "_apply_host_maintenance", lambda *_args, **_kwargs: maintenance.append(True))
    monkeypatch.setattr(update_agent, "_rollback_host_journal", lambda *_args, **_kwargs: None)
    reports = []
    monkeypatch.setattr(update_agent, "_report", lambda _env, _url, _update, state, detail="": reports.append((state, detail)))

    result = update_agent.update_once(tmp_path)

    assert "host maintenance update are healthy" in result
    assert maintenance == [True]
    assert reports == [("applied", "")]
