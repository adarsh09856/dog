from __future__ import annotations

import json
import os
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "deploy/client"))
import recovery  # noqa: E402


def _write_volume_tar(path: Path, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w") as archive:
        payload = f"{name}-data".encode()
        member = tarfile.TarInfo("data/example")
        member.size = len(payload)
        archive.addfile(member, fileobj=__import__("io").BytesIO(payload))


def _installation(directory: Path) -> tuple[Path, Path, Path]:
    inputs_dir = directory / "inputs"
    inputs_dir.mkdir()
    postgres = inputs_dir / "postgres.tar"
    minio = inputs_dir / "minio.tar"
    _write_volume_tar(postgres, "postgres")
    _write_volume_tar(minio, "minio")
    identity = inputs_dir / "installation.key"
    identity.write_bytes(b"k" * 32)
    env = inputs_dir / ".env"
    identity_value = str(identity.resolve())
    manifest_ref = "./client-release-manifest.json"
    manifest_payload = {
        "edition": "client",
        "images": {
            "api": {"reference": "registry.example.com/kodewaves/api@sha256:" + "a" * 64},
            "ui": {"reference": "registry.example.com/kodewaves/ui@sha256:" + "b" * 64},
        },
    }
    manifest = directory / "client-release-manifest.json"
    manifest.write_text(json.dumps({"payload": manifest_payload}), encoding="utf-8")
    release_key = directory / "release-public-key.txt"
    release_key.write_text("release-key\n", encoding="ascii")
    env.write_text(
        "\n".join([
            "KODEWAVES_INSTALLATION_ID=customer-123",
            "KODEWAVES_LICENSE_TOKEN=payload.signature",
            "CLIENT_IDENTITY_KEY_FILE=" + identity_value,
            "CLIENT_IDENTITY_GID=1234",
            "CLIENT_RELEASE_MANIFEST_FILE=" + manifest_ref,
            "CLIENT_API_IMAGE=registry.example.com/kodewaves/api@sha256:" + "a" * 64,
            "CLIENT_UI_IMAGE=registry.example.com/kodewaves/ui@sha256:" + "b" * 64,
            "CLIENT_POSTGRES_IMAGE=registry.example.com/kodewaves/postgres@sha256:" + "c" * 64,
            "CLIENT_MINIO_IMAGE=registry.example.com/kodewaves/minio@sha256:" + "d" * 64,
            "CLIENT_REDIS_IMAGE=registry.example.com/kodewaves/redis@sha256:" + "e" * 64,
            "CLIENT_COTURN_IMAGE=registry.example.com/kodewaves/coturn@sha256:" + "f" * 64,
            "CLIENT_CADDY_IMAGE=registry.example.com/kodewaves/caddy@sha256:" + "1" * 64,
            "COMPOSE_PROFILES=direct-ingress",
            "COMPOSE_PROJECT_NAME=customer-prod",
        ]) + "\n",
        encoding="utf-8",
    )
    return env, manifest, release_key


def _make_archive(tmp_path: Path, env: Path, manifest: Path, release_key: Path, key: Path) -> Path:
    inputs_dir = env.parent
    archive = tmp_path / "recovery.tar.gz"
    recovery.create_archive(
        postgres_tar=inputs_dir / "postgres.tar",
        minio_tar=inputs_dir / "minio.tar",
        env_file=env,
        manifest=manifest,
        release_public_key=release_key,
        output=archive,
        identity_key=key,
        writers_stopped=True,
    )
    return archive


def _compose_model(directory: Path) -> dict[str, object]:
    override = directory / recovery.RECOVERY_OVERRIDE
    if override.exists():
        selected = json.loads(override.read_text()).get("volumes", {})
    else:
        selected = {}
    names = {
        "postgres_data": "customer-prod_postgres_data",
        "minio_data": "customer-prod_minio_data",
        "redis_data": "customer-prod_redis_data",
    }
    for key, value in selected.items():
        names[key] = value["name"]
    return {
        "name": "customer-prod",
        "services": {name: {} for name in ("api", "ui", "postgres", "minio", "redis", "caddy")},
        "volumes": {key: {"name": name} for key, name in names.items()},
    }


def test_docker_backup_stops_exports_and_restarts_only_previously_running_services(monkeypatch, tmp_path):
    compose_dir = tmp_path / "client"
    compose_dir.mkdir()
    env_file, manifest, release_key = _installation(compose_dir)
    for name in ("docker-compose.client.yaml", "docker-compose.identity.yaml", recovery.RECOVERY_OVERRIDE):
        (compose_dir / name).write_text("{}\n", encoding="utf-8")
    events = []

    monkeypatch.setattr(recovery, "_compose_context", lambda *_: (["docker", "compose"], _compose_model(compose_dir), recovery.parse_env(env_file)))
    monkeypatch.setattr(recovery, "_compose_volume_names", lambda _model: {
        "postgres_data": "customer-prod_postgres_data",
        "minio_data": "customer-prod_minio_data",
        "redis_data": "customer-prod_redis_data",
    })
    monkeypatch.setattr(recovery, "_running_services", lambda *_: ["api", "ui", "postgres", "redis", "minio"])
    monkeypatch.setattr(recovery, "_docker_volume_exists", lambda *_: True)
    monkeypatch.setattr(recovery, "_assert_no_running_volume_consumers", lambda *_: None)

    def run(command, **_kwargs):
        events.append(command)
        return ""

    monkeypatch.setattr(recovery, "_run", run)

    def snapshot(*, host_directory, archive_name, **_kwargs):
        _write_volume_tar(host_directory / archive_name, archive_name.removesuffix(".tar"))
        events.append(["snapshot", archive_name])

    monkeypatch.setattr(recovery, "_volume_tar_command", snapshot)
    monkeypatch.setattr(recovery, "_restart_services", lambda _command, _dir, services: events.append(["start", *services]))
    output = tmp_path / "backup.tar.gz"

    result = recovery.create_docker_backup(
        compose_dir=compose_dir, env_file=env_file, output=output,
        release_public_key=release_key, confirm_maintenance=True,
    )

    assert result["status"] == "created"
    assert result["services_restarted"] == ["api", "ui", "postgres", "redis", "minio"]
    assert events[0][-1] == "stop"
    assert events[-1] == ["start", "api", "ui", "postgres", "redis", "minio"]
    assert recovery.validate_archive(output)["installation_id"] == "customer-123"


def test_docker_backup_refuses_external_writers_and_restarts_project(monkeypatch, tmp_path):
    compose_dir = tmp_path / "client"
    compose_dir.mkdir()
    env_file, _manifest, release_key = _installation(compose_dir)
    for name in ("docker-compose.client.yaml", "docker-compose.identity.yaml", recovery.RECOVERY_OVERRIDE):
        (compose_dir / name).write_text("{}\n", encoding="utf-8")
    events = []
    monkeypatch.setattr(recovery, "_compose_context", lambda *_: (["docker", "compose"], _compose_model(compose_dir), recovery.parse_env(env_file)))
    monkeypatch.setattr(recovery, "_compose_volume_names", lambda _model: {
        "postgres_data": "customer-prod_postgres_data",
        "minio_data": "customer-prod_minio_data",
        "redis_data": "customer-prod_redis_data",
    })
    monkeypatch.setattr(recovery, "_running_services", lambda *_: ["api", "postgres"])
    monkeypatch.setattr(recovery, "_docker_volume_exists", lambda *_: True)
    monkeypatch.setattr(
        recovery, "_assert_no_running_volume_consumers",
        lambda *_: (_ for _ in ()).throw(ValueError("running containers still mount volume")),
    )
    monkeypatch.setattr(recovery, "_run", lambda command, **_kwargs: events.append(command) or "")
    monkeypatch.setattr(recovery, "_restart_services", lambda _command, _dir, services: events.append(["start", *services]))
    output = tmp_path / "blocked.tar.gz"

    with pytest.raises(ValueError, match="running containers still mount volume"):
        recovery.create_docker_backup(
            compose_dir=compose_dir, env_file=env_file, output=output,
            release_public_key=release_key, confirm_maintenance=True,
        )

    assert not output.exists()
    assert events[0][-1] == "stop"
    assert events[-1] == ["start", "api", "postgres"]


def test_restore_to_new_volumes_and_rollback_keeps_both_volume_sets(monkeypatch, tmp_path):
    compose_dir = tmp_path / "client"
    compose_dir.mkdir()
    env_file, manifest, release_key = _installation(compose_dir)
    for name in ("docker-compose.client.yaml", "docker-compose.identity.yaml", recovery.RECOVERY_OVERRIDE):
        (compose_dir / name).write_text("{}\n", encoding="utf-8")
    archive = _make_archive(tmp_path, env_file, manifest, release_key, compose_dir / "inputs/installation.key")
    events = []
    running = ["api", "ui", "postgres", "minio", "redis"]
    monkeypatch.setattr(recovery, "_compose_context", lambda *_: (["docker", "compose"], _compose_model(compose_dir), recovery.parse_env(env_file)))
    monkeypatch.setattr(recovery, "_running_services", lambda *_: list(running))
    monkeypatch.setattr(recovery, "_docker_volume_exists", lambda *_: False)
    monkeypatch.setattr(recovery, "_volume_tar_command", lambda **kwargs: events.append(["volume-copy", kwargs["volume_name"], kwargs["archive_name"]]))
    monkeypatch.setattr(recovery, "_run", lambda command, **_kwargs: events.append(command) or "")

    def switch(_dir, _env, services, **_kwargs):
        events.append(["up", *services, _compose_model(compose_dir)["volumes"]["postgres_data"]["name"]])

    monkeypatch.setattr(recovery, "_switch_compose_up", switch)
    result = recovery.restore_to_docker_volumes(
        archive_path=archive, compose_dir=compose_dir, env_file=env_file,
        confirm_maintenance=True,
    )

    assert result["status"] == "restored_to_new_volumes"
    assert result["original_volumes_preserved"] is True
    assert result["new_volumes"]["postgres_data"] != "customer-prod_postgres_data"
    assert (compose_dir / recovery.RECOVERY_STATE_DIR / "state.json").is_file()
    assert json.loads((compose_dir / recovery.RECOVERY_OVERRIDE).read_text())["volumes"]["postgres_data"]["name"] == result["new_volumes"]["postgres_data"]

    rolled_back = recovery.rollback_docker_restore(
        compose_dir=compose_dir, env_file=env_file, confirm_maintenance=True,
    )

    assert rolled_back["status"] == "rolled_back"
    assert rolled_back["original_volumes_selected"]["postgres_data"] == "customer-prod_postgres_data"
    assert json.loads((compose_dir / recovery.RECOVERY_OVERRIDE).read_text()) == {}
    assert Path(rolled_back["rollback_state"]).is_dir()


@pytest.mark.parametrize("failure_point", ["volume_import", "partial_stop", "override_write", "unhealthy_up", "rollback_failure"])
def test_restore_failure_restores_old_selection_and_retains_original_volumes(monkeypatch, tmp_path, failure_point):
    compose_dir = tmp_path / "client"
    compose_dir.mkdir()
    env_file, manifest, release_key = _installation(compose_dir)
    original_override = b"{}\n"
    for name in ("docker-compose.client.yaml", "docker-compose.identity.yaml"):
        (compose_dir / name).write_text("{}\n", encoding="utf-8")
    (compose_dir / recovery.RECOVERY_OVERRIDE).write_bytes(original_override)
    archive = _make_archive(tmp_path, env_file, manifest, release_key, compose_dir / "inputs/installation.key")
    running = ["api", "ui", "postgres", "minio", "redis"]
    events: list[object] = []
    created: list[str] = []
    switched = 0
    stop_attempts = 0
    override_writes = 0

    monkeypatch.setattr(recovery, "_compose_context", lambda *_: (["docker", "compose"], _compose_model(compose_dir), recovery.parse_env(env_file)))
    monkeypatch.setattr(recovery, "_running_services", lambda *_: list(running))
    monkeypatch.setattr(recovery, "_docker_volume_exists", lambda *_: False)
    monkeypatch.setattr(recovery, "_create_volume", lambda name, *_: created.append(name))

    def volume_copy(**kwargs):
        events.append(["volume-copy", kwargs["volume_name"]])
        if failure_point == "volume_import":
            raise RuntimeError("injected import failure")

    monkeypatch.setattr(recovery, "_volume_tar_command", volume_copy)

    def run(command, **_kwargs):
        nonlocal stop_attempts
        events.append(command)
        if command[-1] == "stop":
            stop_attempts += 1
            if failure_point == "partial_stop" and stop_attempts == 1:
                raise RuntimeError("injected partial stop")
        return ""

    monkeypatch.setattr(recovery, "_run", run)

    def atomic_write(path, content, **kwargs):
        nonlocal override_writes
        if path == compose_dir / recovery.RECOVERY_OVERRIDE:
            override_writes += 1
            if failure_point == "override_write" and override_writes == 1:
                raise OSError("injected override write failure")
        return original_atomic_write(path, content, **kwargs)

    original_atomic_write = recovery._atomic_write
    monkeypatch.setattr(recovery, "_atomic_write", atomic_write)
    monkeypatch.setattr(
        recovery, "_remove_owned_recovery_volumes",
        lambda names, _directory, _recovery_id: events.append(["remove-created-only", *names]) or names,
    )

    def switch(_dir, _env, services, **_kwargs):
        nonlocal switched
        switched += 1
        events.append(["up", *services])
        if failure_point == "unhealthy_up" and switched == 1:
            raise RuntimeError("injected unhealthy startup")
        if failure_point == "rollback_failure" and switched <= 2:
            raise RuntimeError("injected unhealthy startup")

    monkeypatch.setattr(recovery, "_switch_compose_up", switch)

    expected_error = "automatic rollback could not restart" if failure_point == "rollback_failure" else "Restore failed"
    with pytest.raises(RuntimeError, match=expected_error):
        recovery.restore_to_docker_volumes(
            archive_path=archive, compose_dir=compose_dir, env_file=env_file,
            confirm_maintenance=True,
        )

    assert (compose_dir / recovery.RECOVERY_OVERRIDE).read_bytes() == original_override
    assert ["up", *running] in events
    cleanup_events = [event for event in events if isinstance(event, list) and event[0] == "remove-created-only"]
    assert "customer-prod_postgres_data" not in str(cleanup_events)
    assert "customer-prod_minio_data" not in str(cleanup_events)
    assert len(created) == 3
    if failure_point == "rollback_failure":
        state = json.loads((compose_dir / recovery.RECOVERY_STATE_DIR / "state.json").read_text())
        assert state["status"] == "automatic_rollback_failed"
        assert cleanup_events == []
        assert set(state["created_volumes"]) == set(created)
    else:
        assert len(cleanup_events) == 1
        assert set(cleanup_events[0][1:]) == set(created)
