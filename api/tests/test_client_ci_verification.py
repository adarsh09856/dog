"""CI signing material must stay disposable and never publish customer releases."""

import json
import re
import subprocess
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest


def _write_fake_build_outputs(command):
    image_id = "sha256:" + "a" * 64
    payload = {
        "edition": "client",
        "files": {"api/app.py": "b" * 64, "api/services/app.py": "c" * 64},
        "ui_files": {".next/server/app.js": "d" * 64},
        "images": {
            "api": {"kind": "image_id", "reference": image_id},
            "ui": {"kind": "image_id", "reference": image_id},
        },
    }
    Path(command[command.index("--manifest-output") + 1]).write_text(json.dumps({"payload": payload, "signature": "test"}))
    Path(command[command.index("--inventory-metrics-output") + 1]).write_text(json.dumps({
        "api": {"file_count": 2, "elapsed_ms": 840.5},
        "ui": {"file_count": 1, "elapsed_ms": 121.0},
    }))


@pytest.fixture
def verifier(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "deploy/client"))
    import ci_verify
    return ci_verify


def test_ci_verifies_without_publishing_or_retaining_signing_material(verifier, monkeypatch, tmp_path):
    captured_keys = []
    commands = []
    root = Path(__file__).resolve().parents[2]

    def run(command, **kwargs):
        commands.append(command)
        if "build_and_verify.py" in command[1]:
            assert "--push" not in command
            private = Path(command[command.index("--owner-private-key") + 1])
            assert not private.is_relative_to(root)
            assert len(private.read_bytes()) == 32
            captured_keys.append(private)
            _write_fake_build_outputs(command)
            return SimpleNamespace(returncode=0)
        if command[:2] == ["docker", "compose"]:
            if "config" in command:
                env_file = Path(command[command.index("--env-file") + 1])
                contents = env_file.read_text()
                assert "COMPOSE_PROFILES=direct-ingress" in contents
                assert "KODEWAVES_LICENSE_TOKEN=ci-payload.ci-signature" in contents
                manifest_path = Path(contents.split("CLIENT_RELEASE_MANIFEST_FILE=", 1)[1].splitlines()[0])
                config_manifest = json.loads(manifest_path.read_text())
                assert config_manifest["ci_configuration_fixture"] is True
                assert "signature" not in config_manifest
                assert config_manifest["payload"]["images"]["api"]["kind"] == "registry_digest"
            if command[-3:] == ["config", "--format", "json"]:
                contents = env_file.read_text()
                if any(str(argument).endswith("docker-compose.identity.yaml") for argument in command):
                    assert "CLIENT_IDENTITY_KEY_FILE=" in contents
                    assert "CLIENT_IDENTITY_GID=" in contents
                    key_path = contents.split("CLIENT_IDENTITY_KEY_FILE=", 1)[1].splitlines()[0]
                    assert Path(key_path).read_bytes() == b"i" * 32
                    gid = contents.split("CLIENT_IDENTITY_GID=", 1)[1].splitlines()[0]
                    mount = {
                        "type": "bind", "source": key_path,
                        "target": "/run/kodewaves-identity/installation.key",
                        # Compose versions may omit false-valued options.
                        "read_only": True, "bind": {},
                    }
                    return SimpleNamespace(stdout=json.dumps({"services": {
                        name: {
                            "group_add": [gid], "volumes": [mount],
                            "environment": {"KODEWAVES_INSTALLATION_KEY_FILE": mount["target"]},
                        }
                        for name in ("api", "ui")
                    }}))
                assert "CLIENT_CADDY_IPV4=172.31.40.2" in contents
                assert "FORWARDED_ALLOW_IPS=" not in contents
                return SimpleNamespace(stdout=json.dumps({"services": {
                    "caddy": {"networks": {"internal": {"ipv4_address": "172.31.40.2"}}},
                    "api": {"environment": {"FORWARDED_ALLOW_IPS": "172.31.40.2"}},
                }}))
            if command[-2:] == ["config", "--quiet"]:
                return SimpleNamespace(returncode=0)
            if "up" in command:
                assert "--wait" in command
                override = Path(command[command.index("-f", command.index("-f") + 1) + 1])
                assert "internal: true" in override.read_text()
                env_values = dict(
                    line.split("=", 1)
                    for line in Path(command[command.index("--env-file") + 1]).read_text().splitlines()
                )
                assert env_values["COMPOSE_PROFILES"] == ""
                assert env_values["KODEWAVES_LICENSE_TOKEN"] == "invalid-ci-license.signature"
                assert "@sha256:" in env_values["CLIENT_POSTGRES_IMAGE"]
                assert "@sha256:" in env_values["CLIENT_REDIS_IMAGE"]
                assert kwargs["env"]["COMPOSE_PROFILES"] == ""
                return SimpleNamespace(returncode=0)
            if "port" in command:
                service = command[command.index("port") + 1]
                return SimpleNamespace(stdout="127.0.0.1:12345\n" if service == "api" else "127.0.0.1:12346\n")
            if "down" in command:
                assert "--volumes" in command and "--remove-orphans" in command
                return SimpleNamespace(returncode=0)
            if "logs" in command:
                return SimpleNamespace(returncode=0)
            pytest.fail(f"Unexpected Compose command: {command}")
        if command[:2] == ["docker", "build"]:
            assert Path(command[command.index("--file") + 1]).name == "Dockerfile"
            return SimpleNamespace(returncode=0)
        if command[:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(stdout="sha256:" + "a" * 64)
        if command[:3] == ["docker", "image", "rm"]:
            return SimpleNamespace(returncode=0)
        pytest.fail(f"Unexpected command: {command}")

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    requested_urls = []

    def open_url(request, timeout):
        requested_urls.append(request.full_url)
        if request.full_url.endswith("/api/v1/workflow"):
            assert request.get_header("Host") == "smoke.customer.example.invalid"
            raise urllib.error.HTTPError(request.full_url, 402, "invalid license", {}, None)
        return Response()

    monkeypatch.setattr(verifier.subprocess, "run", run)
    monkeypatch.setattr(verifier.urllib.request, "urlopen", open_url)
    report = tmp_path / "evidence.json"
    verifier.verify("registry.example.com/kodewaves/caddy@sha256:" + "b" * 64, report)

    evidence = json.loads(report.read_text())
    assert evidence["status"] == "passed"
    assert evidence["production_release"] is False
    assert evidence["installer_preflight"] == "passed"
    assert evidence["compose_config"] == "passed"
    assert evidence["custom_network_proxy_config"] == "passed"
    assert evidence["identity_overlay_config"] == "passed"
    assert evidence["runtime_compose_smoke"]["api_health"] == "passed"
    assert evidence["runtime_compose_smoke"]["ui_root"] == "passed"
    assert evidence["runtime_compose_smoke"]["invalid_license_protected_route"] == "rejected_with_http_402"
    assert "@sha256:" in evidence["runtime_compose_smoke"]["dependency_images"]["postgres"]
    assert "@sha256:" in evidence["runtime_compose_smoke"]["dependency_images"]["redis"]
    assert "Unsigned configuration fixture" in evidence["installer_manifest_scope"]
    assert evidence["protected_inventory"] == {
        "api": {"file_count": 2, "elapsed_ms": 840.5},
        "ui": {"file_count": 1, "elapsed_ms": 121.0},
    }
    assert "telephone" in evidence["not_verified"]
    assert any(
        item.startswith("owner-enrolled clean installation")
        for item in evidence["not_verified"]
    )
    assert "Compose runtime smoke" in evidence["scope"]
    assert any(command[:2] == ["docker", "build"] for command in commands)
    assert any(command[:2] == ["docker", "compose"] and "down" in command for command in commands)
    assert len(requested_urls) == 3
    assert all(url.startswith("http://127.0.0.1:") for url in requested_urls)
    assert captured_keys and all(not key.exists() for key in captured_keys)
    assert "private" not in report.read_text()


def test_ci_failure_does_not_write_success_report_and_removes_keys(verifier, monkeypatch, tmp_path):
    keys = []

    def fail(command, **kwargs):
        keys.append(Path(command[command.index("--owner-private-key") + 1]))
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(verifier.subprocess, "run", fail)
    report = tmp_path / "failed.json"
    with pytest.raises(subprocess.CalledProcessError):
        verifier.verify("registry.example.com/kodewaves/caddy@sha256:" + "b" * 64, report)
    assert not report.exists()
    assert all(not key.exists() for key in keys)


def test_ci_rejects_rendered_custom_proxy_trust_mismatch(verifier, monkeypatch, tmp_path):
    def run(command, **kwargs):
        if "build_and_verify.py" in command[1]:
            _write_fake_build_outputs(command)
            return SimpleNamespace(returncode=0)
        if command[-3:] == ["config", "--format", "json"]:
            return SimpleNamespace(stdout=json.dumps({"services": {
                "caddy": {"networks": {"internal": {"ipv4_address": "172.31.40.2"}}},
                "api": {"environment": {"FORWARDED_ALLOW_IPS": "172.30.0.2"}},
            }}))
        assert command[-2:] == ["config", "--quiet"]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(verifier.subprocess, "run", run)
    report = tmp_path / "wrong-proxy.json"
    with pytest.raises(ValueError, match="proxy trust does not match"):
        verifier.verify("registry.example.com/kodewaves/caddy@sha256:" + "b" * 64, report)
    assert not report.exists()


def test_ci_rejects_writable_enrolled_identity_mount(verifier, monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[2]

    def run(command, **kwargs):
        if command[-3:] == ["config", "--format", "json"]:
            if any(str(argument).endswith("docker-compose.identity.yaml") for argument in command):
                env = Path(command[command.index("--env-file") + 1]).read_text()
                key_path = env.split("CLIENT_IDENTITY_KEY_FILE=", 1)[1].splitlines()[0]
                gid = env.split("CLIENT_IDENTITY_GID=", 1)[1].splitlines()[0]
                return SimpleNamespace(stdout=json.dumps({"services": {
                    name: {
                        "group_add": [gid],
                        "volumes": [{
                            "type": "bind", "source": key_path,
                            "target": "/run/kodewaves-identity/installation.key",
                            "read_only": name != "api",
                            "bind": {"create_host_path": False},
                        }],
                        "environment": {
                            "KODEWAVES_INSTALLATION_KEY_FILE": "/run/kodewaves-identity/installation.key"
                        },
                    }
                    for name in ("api", "ui")
                }}))
            return SimpleNamespace(stdout=json.dumps({"services": {
                "caddy": {"networks": {"internal": {"ipv4_address": "172.31.40.2"}}},
                "api": {"environment": {"FORWARDED_ALLOW_IPS": "172.31.40.2"}},
            }}))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(verifier.subprocess, "run", run)
    with pytest.raises(ValueError, match="API identity key mount is not read-only"):
        verifier._verify_installer_config(
            root, tmp_path, "registry.example.com/kodewaves/caddy@sha256:" + "b" * 64
        )


def test_ci_compose_failure_does_not_write_success_report(verifier, monkeypatch, tmp_path):
    keys = []

    def run(command, **kwargs):
        if "build_and_verify.py" in command[1]:
            private = Path(command[command.index("--owner-private-key") + 1])
            keys.append(private)
            _write_fake_build_outputs(command)
            return SimpleNamespace(returncode=0)
        if command[:2] == ["docker", "compose"]:
            raise subprocess.CalledProcessError(1, command)
        return SimpleNamespace(stdout="sha256:" + "a" * 64)

    monkeypatch.setattr(verifier.subprocess, "run", run)
    report = tmp_path / "compose-failed.json"
    with pytest.raises(subprocess.CalledProcessError):
        verifier.verify("registry.example.com/kodewaves/caddy@sha256:" + "b" * 64, report)
    assert not report.exists()
    assert keys and all(not key.exists() for key in keys)


def test_ci_preflight_failure_does_not_run_compose_or_write_report(verifier, monkeypatch, tmp_path):
    keys = []

    def run(command, **kwargs):
        if "build_and_verify.py" in command[1]:
            private = Path(command[command.index("--owner-private-key") + 1])
            keys.append(private)
            _write_fake_build_outputs(command)
            return SimpleNamespace(returncode=0)
        if command[:2] == ["docker", "compose"]:
            pytest.fail("Compose must not run after installer preflight failure")
        return SimpleNamespace(stdout="sha256:" + "a" * 64)

    monkeypatch.setattr(verifier.subprocess, "run", run)
    monkeypatch.setattr(verifier, "validate_client_install", lambda *_: ["invalid test input"])
    report = tmp_path / "preflight-failed.json"
    with pytest.raises(ValueError, match="installer preflight failed"):
        verifier.verify("registry.example.com/kodewaves/caddy@sha256:" + "b" * 64, report)
    assert not report.exists()
    assert keys and all(not key.exists() for key in keys)


def test_runtime_smoke_always_removes_project_volumes_and_minio_image_on_http_failure(
    verifier, monkeypatch, tmp_path
):
    commands = []
    command_options = []

    def run(command, **kwargs):
        commands.append(command)
        command_options.append((command, kwargs))
        if command[:2] == ["docker", "build"]:
            return SimpleNamespace(returncode=0)
        if command[:2] == ["docker", "compose"]:
            if "port" in command:
                return SimpleNamespace(stdout="127.0.0.1:23456\n")
            return SimpleNamespace(returncode=0)
        if command[:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(stdout="sha256:" + "f" * 64)
        if command[:3] == ["docker", "image", "rm"]:
            return SimpleNamespace(returncode=0)
        pytest.fail(f"Unexpected command: {command}")

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def open_url(request, timeout):
        if request.full_url.endswith("/api/v1/workflow"):
            raise urllib.error.HTTPError(request.full_url, 500, "unexpected response", {}, None)
        return Response()

    monkeypatch.setattr(verifier.subprocess, "run", run)
    monkeypatch.setattr(verifier.urllib.request, "urlopen", open_url)
    with pytest.raises(ValueError, match="received HTTP 500"):
        verifier._verify_compose_runtime(
            Path("/repo"), tmp_path, api_image="kodewaves-api:ci-check",
            ui_image="kodewaves-ui:ci-check", manifest=tmp_path / "manifest.json",
        )

    down = next(command for command in commands if command[:2] == ["docker", "compose"] and "down" in command)
    image_rm = next(command for command in commands if command[:3] == ["docker", "image", "rm"])
    compose_up_options = next(
        options for command, options in command_options
        if command[:2] == ["docker", "compose"] and "up" in command
    )
    assert compose_up_options["capture_output"] is True
    assert compose_up_options["text"] is True
    assert "--volumes" in down and "--remove-orphans" in down
    assert image_rm[-1].startswith("kodewaves-ci-minio:kw-ci-")


def test_runtime_smoke_preserves_compose_startup_diagnostics(verifier, monkeypatch, tmp_path):
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        if command[:2] == ["docker", "build"]:
            return SimpleNamespace(returncode=0)
        if command[:2] == ["docker", "compose"] and "up" in command:
            assert kwargs["capture_output"] is True
            assert kwargs["text"] is True
            raise subprocess.CalledProcessError(1, command, stderr="api healthcheck failed")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(verifier.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError) as error:
        verifier._verify_compose_runtime(
            Path("/repo"), tmp_path, api_image="kodewaves-api:ci-check",
            ui_image="kodewaves-ui:ci-check", manifest=tmp_path / "manifest.json",
        )

    assert error.value.stderr == "api healthcheck failed"
    down = next(
        command for command, _ in commands
        if command[:2] == ["docker", "compose"] and "down" in command
    )
    assert "--volumes" in down and "--remove-orphans" in down


def test_ci_rejects_floating_ingress_image_before_building(verifier, monkeypatch, tmp_path):
    monkeypatch.setattr(verifier.subprocess, "run", lambda *args, **kwargs: pytest.fail("Unexpected build"))
    with pytest.raises(ValueError, match="immutable"):
        verifier.verify("caddy:latest", tmp_path / "evidence.json")


def test_ci_expands_official_caddy_digest_for_installer(verifier):
    digest = "a" * 64
    assert verifier.normalize_caddy_image("caddy@sha256:" + digest) == (
        "docker.io/library/caddy@sha256:" + digest
    )
    assert verifier.normalize_caddy_image("registry.example.com/ingress/caddy@sha256:" + digest) == (
        "registry.example.com/ingress/caddy@sha256:" + digest
    )
    with pytest.raises(ValueError, match="full registry path"):
        verifier.normalize_caddy_image("other@sha256:" + digest)


def test_ci_does_not_reuse_a_stale_success_report(verifier, monkeypatch, tmp_path):
    report = tmp_path / "evidence.json"
    report.write_text("old result")
    monkeypatch.setattr(verifier.subprocess, "run", lambda *args, **kwargs: pytest.fail("Unexpected build"))
    with pytest.raises(ValueError, match="already exists"):
        verifier.verify("registry.example.com/kodewaves/caddy@sha256:" + "b" * 64, report)
    assert report.read_text() == "old result"


def test_ci_rejects_incomplete_or_invalid_inventory_metrics(verifier, tmp_path):
    metrics = tmp_path / "inventory.json"
    metrics.write_text(json.dumps({"api": {"file_count": 0, "elapsed_ms": -1}}))

    with pytest.raises(ValueError, match="both protected inventories"):
        verifier._read_inventory_metrics(metrics)

    metrics.write_text(json.dumps({
        "api": {"file_count": 0, "elapsed_ms": 1},
        "ui": {"file_count": 1, "elapsed_ms": 1},
    }))
    with pytest.raises(ValueError, match="Invalid protected inventory metrics for api"):
        verifier._read_inventory_metrics(metrics)


def test_cli_emits_bounded_ci_annotation_on_failure(verifier, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(sys, "argv", [
        "ci_verify", "--caddy-image", "registry.example.com/ingress@sha256:" + "a" * 64,
        "--report", str(tmp_path / "report.json"),
    ])

    def fail(_caddy_image, _report):
        raise ValueError("runtime smoke failed\nlocal diagnostics")

    monkeypatch.setattr(verifier, "verify", fail)
    with pytest.raises(ValueError, match="runtime smoke failed"):
        verifier.main()

    assert "::error title=Client image verification failed::ValueError: runtime smoke failed%0Alocal diagnostics" in capsys.readouterr().err


def test_cli_reports_redacted_subprocess_diagnostics_in_ci(verifier, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(sys, "argv", [
        "ci_verify", "--caddy-image", "registry.example.com/ingress@sha256:" + "a" * 64,
        "--report", str(tmp_path / "report.json"),
    ])

    def fail(_caddy_image, _report):
        raise subprocess.CalledProcessError(
            1, ["docker", "compose", "up"], stderr="api unhealthy\npassword=test-secret"
        )

    monkeypatch.setattr(verifier, "verify", fail)
    with pytest.raises(subprocess.CalledProcessError):
        verifier.main()

    annotation = capsys.readouterr().err
    assert "api unhealthy" in annotation
    assert "password=[REDACTED]" in annotation
    assert "test-secret" not in annotation
    assert len(annotation) < 1400


def test_owner_ci_installs_same_pipecat_extras_as_api_image():
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "api" / "Dockerfile").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "client-bundle-verification.yml").read_text(encoding="utf-8")
    image_extras = re.search(r"uv pip install '/tmp/pipecat\[([^]]+)\]'", dockerfile)
    ci_extras = re.search(r"pip install './pipecat\[([^]]+)\]'", workflow)

    assert image_extras is not None
    assert ci_extras is not None
    assert ci_extras.group(1) == image_extras.group(1)


def test_client_production_cors_is_bound_to_public_origin():
    import yaml

    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load(
        (root / "deploy/client/docker-compose.client.yaml").read_text(encoding="utf-8")
    )
    environment = compose["services"]["api"]["environment"]
    assert environment["DEPLOYMENT_MODE"] == "production"
    assert environment["CORS_ALLOWED_ORIGINS"] == environment["UI_APP_URL"]
    assert environment["CORS_ALLOWED_ORIGINS"] == "https://${PUBLIC_HOST:?Set licensed public host}"


@pytest.mark.parametrize("tamper", ["api_count", "ui_image", "edition"])
def test_ci_requires_evidence_to_match_signed_manifest(verifier, tmp_path, tamper):
    manifest = tmp_path / "release.json"
    image_id = "sha256:" + "a" * 64
    payload = {
        "edition": "client",
        "files": {"api/app.py": "b" * 64},
        "ui_files": {".next/server/app.js": "c" * 64},
        "images": {
            "api": {"kind": "image_id", "reference": image_id},
            "ui": {"kind": "image_id", "reference": image_id},
        },
    }
    metrics = {
        "api": {"file_count": 1, "elapsed_ms": 10},
        "ui": {"file_count": 1, "elapsed_ms": 5},
    }
    if tamper == "api_count":
        metrics["api"]["file_count"] = 2
    elif tamper == "ui_image":
        payload["images"]["ui"]["reference"] = "sha256:" + "f" * 64
    else:
        payload["edition"] = "saas"
    manifest.write_text(json.dumps({"payload": payload, "signature": "irrelevant"}))

    if tamper == "edition":
        expected = "missing its client payload"
    elif tamper == "api_count":
        expected = "API inventory metrics do not match"
    else:
        expected = "Signed UI image ID does not match"
    with pytest.raises(ValueError, match=expected):
        verifier._verify_manifest_evidence(manifest, metrics, {"api": image_id, "ui": image_id})
