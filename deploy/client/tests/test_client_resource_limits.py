from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "deploy/client/docker-compose.client.yaml"
ENV_EXAMPLE = ROOT / "deploy/client/.env.example"


def test_customer_platform_services_have_bounded_cpu_and_memory_defaults() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = compose["services"]
    expected = {
        "caddy": ("0.25", "256m"),
        "postgres": ("1.0", "1g"),
        "redis": ("0.5", "256m"),
        "minio": ("0.5", "512m"),
        "coturn": ("0.5", "256m"),
        "api": ("1.5", "2g"),
        "ui": ("0.5", "512m"),
    }

    for service, (cpu, memory) in expected.items():
        assert services[service]["cpus"] == f"${{CLIENT_{service.upper()}_CPUS:-{cpu}}}"
        assert services[service]["mem_limit"] == (
            f"${{CLIENT_{service.upper()}_MEMORY_LIMIT:-{memory}}}"
        )

    example = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "separately run model servers" in " ".join(example.split())
    for service in expected:
        prefix = service.upper()
        assert f"# CLIENT_{prefix}_CPUS=" in example
        assert f"# CLIENT_{prefix}_MEMORY_LIMIT=" in example
