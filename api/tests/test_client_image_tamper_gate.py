"""A Docker error or unrelated runtime failure must never count as tamper enforcement."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def image_gate(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "deploy/client"))
    import verify_images

    manifest = tmp_path / "release.json"
    manifest.write_text(json.dumps({"payload": {"images": {
        component: {"kind": "image_id", "reference": "sha256:" + "a" * 64}
        for component in ("api", "ui")
    }}, "signature": "original"}))
    return verify_images, manifest


def test_image_gate_requires_four_specific_rejections_without_changing_release(image_gate, monkeypatch):
    verifier, manifest = image_gate
    original = manifest.read_bytes()
    commands = []
    errors = iter((
        "Protected client release files differ from the signed manifest",
        "Client release manifest is missing or invalid",
        "Client UI integrity check failed: .next/server/app-paths-manifest.json",
        "Client release manifest signature is invalid",
    ))

    def run(command, **kwargs):
        assert command[:6] == ["docker", "run", "--rm", "--network", "none", "--read-only"]
        assert kwargs["timeout"] == 90
        assert not any("LICENSE_TOKEN" in item for item in command)
        commands.append(command)
        return SimpleNamespace(returncode=1, stdout="", stderr=next(errors))

    monkeypatch.setattr(verifier.subprocess, "run", run)
    verifier.verify_startup_rejection("api:test", "ui:test", manifest)
    assert len(commands) == 4
    assert manifest.read_bytes() == original


@pytest.mark.parametrize("code,detail", [
    (0, "Protected client release files differ from the signed manifest"),
    (125, "Protected client release files differ from the signed manifest"),
    (1, "ModuleNotFoundError: dependency missing"),
])
def test_image_gate_refuses_success_or_unrelated_failures(image_gate, monkeypatch, code, detail):
    verifier, manifest = image_gate
    monkeypatch.setattr(verifier.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=code, stdout="", stderr=detail,
    ))
    with pytest.raises(ValueError, match="startup rejection was not proved"):
        verifier.verify_startup_rejection("api:test", "ui:test", manifest)
