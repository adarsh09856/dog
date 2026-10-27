"""The owner signer is mounted only in the owner API deployment."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_owner_signer_mount_is_read_only_and_absent_from_client_stack():
    owner = yaml.safe_load((ROOT / "deploy/owner/docker-compose.owner.yaml").read_text())
    assert set(owner["services"]) == {"api"}
    api = owner["services"]["api"]
    assert api["environment"]["KODEWAVES_EDITION"] == "saas"
    assert api["environment"]["KODEWAVES_OWNER_LICENSE_SIGNING_KEY_FILE"] == (
        "/run/kodewaves-owner-keys/current.key"
    )
    mount = api["volumes"][0]
    assert mount["type"] == "bind"
    assert mount["source"].startswith("${KODEWAVES_OWNER_KEYS_DIR:?")
    assert mount["target"] == "/run/kodewaves-owner-keys"
    assert mount["read_only"] is True
    assert mount["bind"]["create_host_path"] is False

    client = (ROOT / "deploy/client/docker-compose.client.yaml").read_text()
    assert "KODEWAVES_OWNER_LICENSE_SIGNING_KEY_FILE" not in client
    assert "/run/kodewaves-owner-keys" not in client


@pytest.mark.parametrize("owner_enabled", [False, True])
def test_deploy_reuses_owner_overlay_when_configured(tmp_path, owner_enabled):
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is required to exercise deploy.sh")
    shutil.copy2(ROOT / "deploy.sh", tmp_path / "deploy.sh")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake_git = bindir / "git"
    fake_git.write_text("#!/usr/bin/env bash\nprintf '%s\\n' fixture-revision\n", encoding="utf-8")
    fake_docker = bindir / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$MOCK_DOCKER_LOG\"\n"
        "case \"$*\" in *pg_dump*) printf '%s\\n' fixture-backup;; esac\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    fake_docker.chmod(0o755)
    (tmp_path / ".env").write_text(
        "KODEWAVES_OWNER_KEYS_DIR=/owner-keys\n" if owner_enabled else "",
        encoding="utf-8",
    )
    log = tmp_path / "docker.log"
    env = os.environ.copy()
    env.pop("KODEWAVES_OWNER_KEYS_DIR", None)
    env.update({
        "MOCK_DOCKER_LOG": str(log),
        "COMPOSE_FILE": "docker-compose.yaml",
        "ENABLE_LOCAL_AI_ENGINE": "false",
    })
    run_script = (
        'workspace="$1"; '
        'if command -v cygpath >/dev/null 2>&1; then workspace="$(cygpath -u "$workspace")"; fi; '
        'export MOCK_DOCKER_LOG="$workspace/docker.log"; '
        'export PATH="$workspace/bin:$PATH"; '
        'exec bash "$workspace/deploy.sh"'
    )
    result = subprocess.run(
        [bash, "-c", run_script, "bash", str(tmp_path)], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    commands = log.read_text(encoding="utf-8").splitlines()
    assert commands
    assert all(
        ("-f deploy/owner/docker-compose.owner.yaml" in command) is owner_enabled
        for command in commands if command.startswith("compose ")
    )
