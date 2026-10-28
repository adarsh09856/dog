"""CI signing material must stay disposable and never publish customer releases."""

import json
import subprocess
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
            assert command[-2:] == ["config", "--quiet"]
            return SimpleNamespace(returncode=0)
        assert command[:3] == ["docker", "image", "inspect"]
        return SimpleNamespace(stdout="sha256:" + "a" * 64)

    monkeypatch.setattr(verifier.subprocess, "run", run)
    report = tmp_path / "evidence.json"
    verifier.verify("registry.example.com/kodewaves/caddy@sha256:" + "b" * 64, report)

    evidence = json.loads(report.read_text())
    assert evidence["status"] == "passed"
    assert evidence["production_release"] is False
    assert evidence["installer_preflight"] == "passed"
    assert evidence["compose_config"] == "passed"
    assert evidence["custom_network_proxy_config"] == "passed"
    assert evidence["identity_overlay_config"] == "passed"
    assert "Unsigned configuration fixture" in evidence["installer_manifest_scope"]
    assert evidence["protected_inventory"] == {
        "api": {"file_count": 2, "elapsed_ms": 840.5},
        "ui": {"file_count": 1, "elapsed_ms": 121.0},
    }
    assert "telephone" in evidence["not_verified"]
    assert "Compose interpolation" in evidence["scope"]
    assert len(commands) == 6
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
