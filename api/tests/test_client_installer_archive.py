import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


@pytest.fixture
def package_inputs(monkeypatch, tmp_path):
    repository = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(repository / "owner-tools"))
    import package_client_installer as packager

    root = tmp_path / "source"
    directory = root / "deploy/client"
    directory.mkdir(parents=True)
    for name in ("INSTALL.md", "docker-compose.client.yaml", "docker-compose.identity.yaml", "Caddyfile", "validate_install.py", ".env.example"):
        shutil.copy2(repository / "deploy/client" / name, directory / name)
    (directory / ".env").write_text("KODEWAVES_LICENSE_TOKEN=customer-secret")
    (root / "owner-tools").mkdir()
    (root / "owner-tools/private.key").write_text("private-key-must-never-ship")
    owner_deploy = root / "deploy/owner"
    owner_deploy.mkdir()
    shutil.copy2(repository / "deploy/owner/docker-compose.owner.yaml", owner_deploy)
    (owner_deploy / "owner-secret.key").write_text("owner-signer-must-never-ship")
    images = {
        key: f"registry.example.com/kodewaves/{key.lower()}@sha256:{'a' * 64}"
        for key in packager.IMAGE_KEYS
    }
    images_env = tmp_path / "images.env"
    images_env.write_text("".join(f"{key}={value}\n" for key, value in sorted(images.items())))
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    public_key = tmp_path / "release-public.key"
    public_key.write_text(base64.urlsafe_b64encode(public).rstrip(b"=").decode("ascii"))
    payload = {
        "edition": "client",
        "files": {"api/app.py": "b" * 64},
        "ui_files": {"server.js": "c" * 64},
        "schema_compatibility": {"head": "rev1", "upgrade_from": ["rev1"], "rollback_to": []},
        "images": {
            component: {"kind": "registry_digest", "reference": images[f"CLIENT_{component.upper()}_IMAGE"]}
            for component in ("api", "ui")
        },
    }
    signature = private.sign(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    manifest = tmp_path / "release.json"
    manifest.write_text(json.dumps({
        "payload": payload,
        "signature": base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii"),
    }))
    return packager, root, images, images_env, manifest, public_key, tmp_path / "installer.tar.gz", private


def test_customer_archive_contains_only_installation_files_and_matching_images(package_inputs):
    packager, root, images, images_env, manifest, public_key, output, _ = package_inputs
    packager.package_installer(images_env, manifest, public_key, output, root=root)

    with tarfile.open(output, "r:gz") as archive:
        assert set(archive.getnames()) == {
            "README.md", "docker-compose.client.yaml", "docker-compose.identity.yaml", "Caddyfile", "validate_install.py",
            ".env.example", "client-release-manifest.json", "release-public-key.txt", "SHA256SUMS",
        }
        contents = {name: archive.extractfile(name).read() for name in archive.getnames()}
        assert archive.getmember(".env.example").mode == 0o600
    assert b"customer-secret" not in b"".join(contents.values())
    assert b"private-key-must-never-ship" not in b"".join(contents.values())
    assert b"owner-signer-must-never-ship" not in b"".join(contents.values())
    template = contents[".env.example"].decode("utf-8")
    for key, value in images.items():
        assert f"{key}={value}" in template
    assert contents["client-release-manifest.json"] == manifest.read_bytes()
    for line in contents["SHA256SUMS"].decode("ascii").splitlines():
        digest, name = line.split("  ", 1)
        assert hashlib.sha256(contents[name]).hexdigest() == digest

    extracted = output.parent / "customer-server"
    extracted.mkdir()
    for name, content in contents.items():
        (extracted / name).write_bytes(content)
    values = packager.parse_env(extracted / ".env.example")
    values.update({
        "CLIENT_RELEASE_MANIFEST_FILE": "./client-release-manifest.json",
        "KODEWAVES_INSTALLATION_ID": "installation-123",
        "KODEWAVES_LICENSE_TOKEN": "payload.signature",
        "PUBLIC_HOST": "voice.customer.example.com",
        "TURN_HOST": "8.8.8.8",
        "MINIO_ROOT_USER": "kodewaves-storage",
        "MASTER_CREDENTIAL_ENCRYPTION_KEY": base64.urlsafe_b64encode(b"e" * 32).rstrip(b"=").decode("ascii"),
    })
    for name in ("POSTGRES_PASSWORD", "REDIS_PASSWORD", "MINIO_ROOT_PASSWORD", "OSS_JWT_SECRET", "TELEPHONY_WS_TOKEN_SECRET", "TURN_SECRET"):
        values[name] = "s" * 40
    (extracted / ".env").write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    checked = subprocess.run(
        [sys.executable, "-I", "-S", "validate_install.py"],
        cwd=extracted, capture_output=True, text=True, check=False,
    )
    assert checked.returncode == 0, checked.stderr
    assert "Client installation inputs look valid" in checked.stdout


@pytest.mark.parametrize("problem", ["signature", "image", "floating", "secret", "schema", "port"])
def test_customer_archive_rejects_untrusted_or_unmatched_inputs_without_output(package_inputs, problem):
    packager, root, images, images_env, manifest, public_key, output, private = package_inputs
    if problem == "signature":
        signed = json.loads(manifest.read_text())
        signed["payload"]["files"]["api/app.py"] = "d" * 64
        manifest.write_text(json.dumps(signed))
        error = "signature is invalid"
    elif problem == "image":
        images_env.write_text(images_env.read_text().replace(images["CLIENT_UI_IMAGE"], images["CLIENT_UI_IMAGE"].replace("a" * 64, "b" * 64)))
        error = "Signed UI image does not match"
    elif problem == "floating":
        images_env.write_text(images_env.read_text().replace(images["CLIENT_CADDY_IMAGE"], "caddy:latest"))
        error = "immutable sha256 digest"
    elif problem == "secret":
        with images_env.open("a") as file:
            file.write("KODEWAVES_LICENSE_TOKEN=do-not-ship\n")
        error = "no secrets"
    elif problem == "port":
        images_env.write_text(images_env.read_text().replace("registry.example.com/", "registry.example.com:99999/"))
        error = "registry port must be between"
    else:
        signed = json.loads(manifest.read_text())
        signed["payload"].pop("schema_compatibility")
        signature = private.sign(json.dumps(signed["payload"], sort_keys=True, separators=(",", ":")).encode("utf-8"))
        signed["signature"] = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
        manifest.write_text(json.dumps(signed))
        error = "signed schema compatibility metadata"

    with pytest.raises(ValueError, match=error):
        packager.package_installer(images_env, manifest, public_key, output, root=root)
    assert not output.exists()


def test_customer_archive_never_overwrites_an_existing_delivery(package_inputs):
    packager, root, _, images_env, manifest, public_key, output, _ = package_inputs
    output.write_bytes(b"existing-approved-delivery")
    with pytest.raises(ValueError, match="already exists"):
        packager.package_installer(images_env, manifest, public_key, output, root=root)
    assert output.read_bytes() == b"existing-approved-delivery"
