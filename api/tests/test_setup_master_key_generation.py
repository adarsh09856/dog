from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_COMMON = REPO_ROOT / "scripts" / "lib" / "setup_common.sh"
KNOWN_FALLBACK = "k5Zp9mR8wX2yQ4tL7vN1jF3bH6aC8eD0sU2iO4gA6cY="
BASH = shutil.which("bash")


requires_linux_bash = pytest.mark.skipif(
    sys.platform != "linux" or BASH is None,
    reason="The Bash setup helper integration test runs on Linux CI",
)


def _fake_command(path: Path, name: str, body: str) -> None:
    command = path / name
    command.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    command.chmod(0o755)


def _run_generator(path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{path}:/usr/bin:/bin"
    return subprocess.run(
        [
            BASH or "bash",
            "-c",
            '. "$1"; kodewaves_generate_master_credential_key',
            "test-key-generator",
            str(SETUP_COMMON),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@requires_linux_bash
def test_key_generation_fails_closed_when_crypto_tools_fail(tmp_path: Path) -> None:
    _fake_command(tmp_path, "python3", "exit 1")
    _fake_command(tmp_path, "openssl", "exit 1")

    result = _run_generator(tmp_path)

    assert result.returncode != 0
    assert KNOWN_FALLBACK not in result.stdout + result.stderr
    assert "generate" in result.stderr.lower()


@requires_linux_bash
def test_key_generation_uses_python_and_returns_a_fernet_key(tmp_path: Path) -> None:
    generated = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")
    _fake_command(tmp_path, "python3", f"printf '%s\\n' '{generated}'")
    _fake_command(tmp_path, "openssl", "exit 1")

    result = _run_generator(tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == generated
    assert len(base64.urlsafe_b64decode(result.stdout.strip())) == 32


@requires_linux_bash
def test_key_generation_normalizes_openssl_base64_when_python_fails(tmp_path: Path) -> None:
    standard_base64 = base64.b64encode(bytes([255]) * 32).decode("ascii")
    _fake_command(tmp_path, "python3", "exit 1")
    _fake_command(tmp_path, "openssl", f"printf '%s\\n' '{standard_base64}'")

    result = _run_generator(tmp_path)

    expected = standard_base64.replace("+", "-").replace("/", "_")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected
    assert len(base64.urlsafe_b64decode(result.stdout.strip())) == 32


@requires_linux_bash
def test_previous_master_key_helper_preserves_and_deduplicates_legacy_values() -> None:
    encoded_old = base64.urlsafe_b64encode(b"old-secret").decode().rstrip("=")
    encoded_quoted = base64.urlsafe_b64encode(b" secret, with spaces ").decode().rstrip("=")
    result = subprocess.run(
        [
            BASH or "bash",
            "-c",
            '. "$1"; kodewaves_legacy_master_credential_previous_keys "$2" "$3" "$4" "$5" "$6"',
            "test-legacy-key-migration",
            str(SETUP_COMMON),
            "existing-fernet-key,legacy-b64:" + encoded_old,
            "old-secret",
            '  " secret, with spaces "  ',
            "  trimmed-secret  ",
            "",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "existing-fernet-key,legacy-b64:" + encoded_old
        + ",legacy-b64:" + encoded_quoted
        + ",legacy-b64:" + base64.urlsafe_b64encode(b"trimmed-secret").decode().rstrip("=")
    )


def test_all_setup_variants_use_generated_installation_key() -> None:
    bash_setup = (REPO_ROOT / "scripts" / "setup_local.sh").read_text(encoding="utf-8")
    remote_setup = (REPO_ROOT / "scripts" / "setup_remote.sh").read_text(encoding="utf-8")
    docker_setup = (REPO_ROOT / "scripts" / "start_docker.sh").read_text(encoding="utf-8")
    powershell_setup = (REPO_ROOT / "scripts" / "setup_local.ps1").read_text(encoding="utf-8")
    powershell_docker = (REPO_ROOT / "scripts" / "start_docker.ps1").read_text(encoding="utf-8")
    api_example = (REPO_ROOT / "api" / ".env.example").read_text(encoding="utf-8")

    for source in (bash_setup, remote_setup, docker_setup):
        assert KNOWN_FALLBACK not in source
        assert "kodewaves_generate_master_credential_key" in source

    assert "MASTER_CREDENTIAL_ENCRYPTION_KEY" in powershell_setup
    assert "KODEWAVES_SECRET_KEY" in powershell_setup
    assert "MASTER_CREDENTIAL_ENCRYPTION_KEY" in powershell_docker
    assert "KODEWAVES_SECRET_KEY" in powershell_docker
    assert KNOWN_FALLBACK not in api_example
    assert "<generate-a-unique-url-safe-base64-32-byte-key>" not in api_example
