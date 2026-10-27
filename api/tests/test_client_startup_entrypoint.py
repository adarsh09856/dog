"""Client startup must not hide required initialization failures."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("bash") is None, reason="Bash is required for the Docker entrypoint")
def test_seed_failure_stops_client_entrypoint_before_services_start(tmp_path):
    root = Path(__file__).resolve().parents[2]
    fixture_root = tmp_path / "installation"
    scripts = fixture_root / "scripts"
    fake_bin = tmp_path / "bin"
    scripts.mkdir(parents=True)
    fake_bin.mkdir()
    (fixture_root / "api").mkdir()
    shutil.copy2(root / "scripts/start_services_docker.sh", scripts / "start_services_docker.sh")

    fake_python = fake_bin / "python"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "case \"$*\" in\n"
        "  *api.services.release_integrity*) exit 0 ;;\n"
        "  *scripts.seed_platform*) echo injected-seed-failure >&2; exit 42 ;;\n"
        "  *) echo unexpected-python-call >&2; exit 43 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake_alembic = fake_bin / "alembic"
    fake_alembic.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    for command in (fake_python, fake_alembic):
        command.chmod(0o755)

    environment = {
        **os.environ,
        "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
        "KODEWAVES_EDITION": "client",
        "ENABLE_CAMPAIGN_ORCHESTRATOR": "false",
        "ENABLE_ARI_MANAGER": "false",
        "ARQ_WORKERS": "0",
        "FASTAPI_WORKERS": "1",
    }
    result = subprocess.run(
        [shutil.which("bash"), str(scripts / "start_services_docker.sh")],
        cwd=fixture_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 42, result.stdout + result.stderr
    assert "injected-seed-failure" in result.stderr
    assert "Starting uvicorn" not in result.stdout
