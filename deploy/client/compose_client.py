#!/usr/bin/env python3
"""Run Docker Compose with the client, identity and recovery overlays pinned.

This wrapper rejects options that could replace those files or switch project
and environment selection. `python3 compose_client.py --help` describes the
wrapper without requiring Docker; other arguments are passed to Compose.
"""

from __future__ import annotations

import subprocess
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_install import parse_env, validate as validate_installation
from recovery_lock import recovery_operation_lock

FORBIDDEN_OPTIONS = {"-f", "--file", "--project-directory", "--env-file", "-p", "--project-name"}
SERVICE_START_COMMANDS = {"create", "exec", "restart", "run", "scale", "start", "up"}


def _is_forbidden_option(argument: str) -> bool:
    return argument in FORBIDDEN_OPTIONS or argument.startswith((
        "--file=", "--project-directory=", "--env-file=", "--project-name=",
    )) or (argument.startswith(("-f", "-p")) and argument != "--")


def _project_name(directory: Path, env: dict[str, str]) -> str:
    name = env.get("COMPOSE_PROJECT_NAME") or directory.name.lower()
    if not name or not name[0].isalnum() or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for character in name):
        raise ValueError("Set COMPOSE_PROJECT_NAME in .env to the existing valid Compose project name")
    return name


def build_command(directory: Path, arguments: list[str]) -> list[str]:
    if any(_is_forbidden_option(argument) for argument in arguments):
        raise ValueError("compose_client.py controls Compose files, project directory and .env; remove the override option")
    env_file = directory / ".env"
    if not env_file.is_file():
        raise ValueError("Copy .env.example to .env and configure the client installation first")
    env = parse_env(env_file)
    # Compose permits options before its command, e.g. `--profile x up -d`.
    # Looking only at the first non-option token can mistake an option value
    # for the command and bypass the enrollment gate. Treat any start-capable
    # verb in the argument list as requiring enrollment.
    starts_services = any(item in SERVICE_START_COMMANDS for item in arguments)
    key_reference = env.get("CLIENT_IDENTITY_KEY_FILE", "").strip()
    key_exists = bool(key_reference) and Path(key_reference).is_file()
    if key_reference and not key_exists and starts_services:
        raise ValueError("Enroll the owner-issued installation identity before starting client services")
    if not key_reference and starts_services:
        raise ValueError("Owner enrollment is required before starting or entering client services")
    files = ["docker-compose.client.yaml"]
    if key_exists:
        files.append("docker-compose.identity.yaml")
    files.append("docker-compose.recovery.yaml")
    for name in files:
        target = directory / name
        if not target.is_file() or target.is_symlink():
            raise ValueError(f"Required Compose file is missing or unsafe: {name}")
    command = [
        "docker", "compose", "--project-directory", str(directory.resolve()),
        "--project-name", _project_name(directory, env), "--env-file", str(env_file.resolve()),
    ]
    for name in files:
        command.extend(("-f", str(directory / name)))
    command.extend(arguments)
    return command


def controlled_environment(directory: Path) -> dict[str, str]:
    """Keep shell variables from overriding configured values or Compose defaults."""
    configured = parse_env(directory / ".env")
    interpolated: set[str] = set()
    for name in (
        "docker-compose.client.yaml",
        "docker-compose.identity.yaml",
        "docker-compose.recovery.yaml",
    ):
        path = directory / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Required Compose file is missing or unsafe: {name}")
        interpolated.update(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", path.read_text(encoding="utf-8")))
    forbidden = {
        "COMPOSE_PROJECT_NAME", "COMPOSE_PROFILES", "COMPOSE_FILE",
        "COMPOSE_ENV_FILES", "COMPOSE_PATH_SEPARATOR",
        *configured.keys(), *interpolated,
    }
    return {key: value for key, value in os.environ.items() if key not in forbidden}


def preflight_start(directory: Path, environment: dict[str, str]) -> None:
    """Validate installation inputs and the selected Compose configuration before startup."""
    env_file = directory / ".env"
    compose_file = directory / "docker-compose.client.yaml"
    findings = validate_installation(env_file, compose_file)
    failures = [item for item in findings if not item.startswith("preflight passed;")]
    if failures:
        raise ValueError("Client installation preflight failed: " + "; ".join(failures))

    config_command = build_command(directory, ["config", "--quiet"])
    result = subprocess.run(
        config_command,
        cwd=directory,
        check=False,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise ValueError(
            "Docker Compose configuration check failed; run `python3 compose_client.py config --quiet` for details"
        )


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    directory = Path(__file__).resolve().parent
    if arguments in ([], ["-h"], ["--help"]):
        print(
            "Usage: python3 compose_client.py <docker-compose arguments>\n"
            "Runs Compose with the client, enrolled identity (when present), and\n"
            "persistent recovery overlays. File, project, and env-file overrides\n"
            "are refused; owner enrollment is required before starting services."
        )
        return 0
    try:
        with recovery_operation_lock(directory):
            command = build_command(directory, arguments)
            controlled_env = controlled_environment(directory)
            if any(item in SERVICE_START_COMMANDS for item in arguments):
                preflight_start(directory, controlled_env)
            return subprocess.run(command, cwd=directory, check=False, env=controlled_env).returncode
    except (ValueError, OSError) as exc:
        print(f"Client Compose command rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
