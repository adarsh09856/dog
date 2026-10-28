from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "deploy/client"))
import compose_client  # noqa: E402


def _package(tmp_path: Path, *, identity: bool) -> Path:
    source = ROOT / "deploy/client"
    for name in (
        "docker-compose.client.yaml",
        "docker-compose.identity.yaml",
        "docker-compose.recovery.yaml",
        "validate_install.py",
        "compose_client.py",
        "recovery_lock.py",
    ):
        (tmp_path / name).write_bytes((source / name).read_bytes())
    identity_value = str(tmp_path / "installation.key") if identity else ""
    if identity:
        (tmp_path / "installation.key").write_bytes(b"k" * 32)
    (tmp_path / ".env").write_text(
        f"CLIENT_IDENTITY_KEY_FILE={identity_value}\n"
        f"CLIENT_IDENTITY_GID={'1234' if identity else ''}\n",
        encoding="utf-8",
    )
    return tmp_path


def test_compose_wrapper_always_selects_recovery_override(tmp_path):
    directory = _package(tmp_path, identity=True)

    command = compose_client.build_command(directory, ["up", "-d", "api"])

    assert any(item.endswith("docker-compose.client.yaml") for item in command)
    assert any(item.endswith("docker-compose.identity.yaml") for item in command)
    assert any(item.endswith("docker-compose.recovery.yaml") for item in command)
    assert command[-3:] == ["up", "-d", "api"]


def test_compose_wrapper_uses_base_and_recovery_without_identity(tmp_path):
    directory = _package(tmp_path, identity=False)

    command = compose_client.build_command(directory, ["ps"])

    assert any(item.endswith("docker-compose.client.yaml") for item in command)
    assert any(item.endswith("docker-compose.recovery.yaml") for item in command)
    assert not any(item.endswith("docker-compose.identity.yaml") for item in command)


@pytest.mark.parametrize("argument", ["-f", "--file", "--file=other.yaml", "-p", "-pother", "--project-name"])
def test_compose_wrapper_rejects_file_or_project_override(tmp_path, argument):
    directory = _package(tmp_path, identity=False)

    with pytest.raises(ValueError, match="controls Compose files"):
        compose_client.build_command(directory, ["up", argument])


def test_compose_wrapper_refuses_missing_recovery_overlay(tmp_path):
    directory = _package(tmp_path, identity=False)
    (directory / "docker-compose.recovery.yaml").unlink()

    with pytest.raises(ValueError, match="missing or unsafe"):
        compose_client.build_command(directory, ["ps"])


def test_compose_wrapper_requires_owner_enrollment_before_service_start(tmp_path):
    directory = _package(tmp_path, identity=False)

    with pytest.raises(ValueError, match="Owner enrollment is required"):
        compose_client.build_command(directory, ["up", "-d"])


def test_compose_wrapper_cannot_hide_start_command_after_profile_option(tmp_path):
    directory = _package(tmp_path, identity=False)

    with pytest.raises(ValueError, match="Owner enrollment is required"):
        compose_client.build_command(directory, ["--profile", "direct-ingress", "up", "-d"])


def test_compose_wrapper_allows_image_pull_before_identity_file_exists(tmp_path):
    directory = _package(tmp_path, identity=False)
    (directory / ".env").write_text(
        "CLIENT_IDENTITY_KEY_FILE=/missing/identity.key\nCLIENT_IDENTITY_GID=1234\n",
        encoding="utf-8",
    )

    command = compose_client.build_command(directory, ["pull", "api"])
    assert "docker-compose.identity.yaml" not in command


def test_compose_wrapper_uses_configured_project_name_not_shell_environment(tmp_path, monkeypatch):
    directory = _package(tmp_path, identity=False)
    with (directory / ".env").open("a", encoding="utf-8") as env_file:
        env_file.write("COMPOSE_PROJECT_NAME=customer-stable\n")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "different-shell-project")

    command = compose_client.build_command(directory, ["ps"])

    project_index = command.index("--project-name")
    assert command[project_index + 1] == "customer-stable"


def test_compose_wrapper_environment_cannot_override_dotenv_values(tmp_path, monkeypatch):
    directory = _package(tmp_path, identity=False)
    with (directory / ".env").open("a", encoding="utf-8") as env_file:
        env_file.write("API_PORT=8000\nCOMPOSE_PROFILES=direct-ingress\n")
    monkeypatch.setenv("API_PORT", "9999")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "different-shell-project")
    monkeypatch.setenv("COMPOSE_PROFILES", "")
    monkeypatch.setenv("DOCKER_CONFIG", "C:/docker/config")

    environment = compose_client.controlled_environment(directory)

    assert "API_PORT" not in environment
    assert "COMPOSE_PROJECT_NAME" not in environment
    assert "COMPOSE_PROFILES" not in environment
    assert environment["DOCKER_CONFIG"] == "C:/docker/config"


def test_compose_wrapper_waits_for_recovery_operation_lock(tmp_path, monkeypatch):
    directory = _package(tmp_path, identity=True)
    monkeypatch.setattr(compose_client, "__file__", str(directory / "compose_client.py"))
    command_started = __import__("threading").Event()
    worker_finished = __import__("threading").Event()

    def fake_run(command, **_kwargs):
        command_started.set()
        return compose_client.subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(compose_client.subprocess, "run", fake_run)

    def invoke_wrapper():
        try:
            assert compose_client.main(["up", "-d", "api"]) == 0
        finally:
            worker_finished.set()

    worker = __import__("threading").Thread(target=invoke_wrapper)
    with compose_client.recovery_operation_lock(directory):
        worker.start()
        __import__("time").sleep(0.05)
        assert not command_started.is_set()
    worker.join(timeout=2)

    assert worker_finished.is_set()
    assert command_started.is_set()
