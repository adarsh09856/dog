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
    monkeypatch.syspath_prepend(str(repository / "deploy/client"))
    import package_client_installer as packager

    root = tmp_path / "source"
    directory = root / "deploy/client"
    directory.mkdir(parents=True)
    for name in ("INSTALL.md", "docker-compose.client.yaml", "docker-compose.identity.yaml", "docker-compose.recovery.yaml", "Caddyfile", "validate_install.py", "recovery.py", "compose_client.py", "recovery_lock.py", "enroll_identity.py", "verify_installer.py", "update_agent.py", "kodewaves-client-update.service", "kodewaves-client-update.timer", ".env.example"):
        shutil.copy2(repository / "deploy/client" / name, directory / name)
    third_party = directory / "third-party"
    third_party.mkdir()
    for name in ("AGPL-3.0-PGSTY-Silo.txt", "NOTICE", "CREDITS", "THIRD_PARTY_NOTICES.txt"):
        shutil.copy2(repository / "deploy/client/third-party" / name, third_party / name)
        copied = third_party / name
        copied.write_bytes(copied.read_bytes().replace(b"\r\n", b"\n"))
    source_archive = third_party / packager.SILO_SOURCE_ARCHIVE_NAME
    source_archive.write_bytes(b"test source archive")
    monkeypatch.setattr(packager, "SILO_SOURCE_SHA256", hashlib.sha256(source_archive.read_bytes()).hexdigest())
    notice_path = third_party / "THIRD_PARTY_NOTICES.txt"
    notice_path.write_bytes(
        notice_path.read_bytes().replace(
            b"011653445e59b3d9f01ca482a41e1706ba214d5cac4c254b43543b4fe8d209fc",
            packager.SILO_SOURCE_SHA256.encode("ascii"),
        )
    )
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
    images["CLIENT_MINIO_IMAGE"] = packager.SILO_IMAGE
    images_env = tmp_path / "images.env"
    images_env.write_text("".join(f"{key}={value}\n" for key, value in sorted(images.items())))
    private = Ed25519PrivateKey.generate()
    private_key_file = tmp_path / "release-private.key"
    private_key_file.write_bytes(private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    ))
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
    return packager, root, images, images_env, manifest, public_key, private_key_file, tmp_path / "installer.tar.gz", private


def test_signed_local_inference_archive_roundtrips_through_updater(package_inputs):
    packager, root, images, images_env, manifest, public_key, private_key, output, signing_key = package_inputs
    import verify_installer

    repository = Path(__file__).resolve().parents[2]
    for name in ("docker-compose.models.yaml", "warm_local_models.py"):
        shutil.copy2(repository / "deploy/client" / name, root / "deploy/client" / name)
    images.update({key: "ghcr.io/vendor/model@sha256:" + "d" * 64 for key in packager.MODEL_IMAGE_KEYS})
    images["CLIENT_OLLAMA_MODEL"] = "qwen3.5:2b-q4_K_M"
    images["CLIENT_OLLAMA_MODEL_DIGEST"] = "sha256:" + "9" * 64
    images_env.write_text("".join(f"{key}={value}\n" for key, value in sorted(images.items())))
    signed = json.loads(manifest.read_text(encoding="utf-8"))
    signed["payload"]["model_images"] = {
        component: images[key]
        for component, key in (
            ("ollama", "CLIENT_OLLAMA_IMAGE"),
            ("indic_stt", "CLIENT_INDIC_STT_IMAGE"),
            ("indus_tts", "CLIENT_INDUS_TTS_IMAGE"),
            ("indic_vits_tts", "CLIENT_INDIC_VITS_TTS_IMAGE"),
        )
    }
    signed["payload"]["model_assets"] = {
        "ollama": {"name": "qwen3.5:2b-q4_K_M", "digest": "sha256:" + "9" * 64},
    }
    canonical = json.dumps(signed["payload"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    signed["signature"] = base64.urlsafe_b64encode(signing_key.sign(canonical)).rstrip(b"=").decode("ascii")
    manifest.write_text(json.dumps(signed), encoding="utf-8")
    packager.package_installer(images_env, manifest, public_key, private_key, output, root=root)
    assert output.with_name(output.name + ".sig").is_file()
    assert verify_installer.verify_installer_archive(
        output, output.with_name(output.name + ".sig"), public_key
    ) == hashlib.sha256(output.read_bytes()).hexdigest()
    import update_agent
    extracted = output.parent / "model-extracted"
    update_agent._extract_verified_archive(output, extracted)
    values = update_agent._model_update_values(
        {"COMPOSE_PROFILES": "self-hosted"}, extracted, signed["payload"],
    )
    assert values == {
        **{key: images[key] for key in packager.MODEL_IMAGE_KEYS},
        "CLIENT_OLLAMA_MODEL": "qwen3.5:2b-q4_K_M",
        "CLIENT_OLLAMA_MODEL_DIGEST": "sha256:" + "9" * 64,
    }
    assert (extracted / "warm_local_models.py").is_file()
    installer_env = (extracted / ".env.example").read_text(encoding="utf-8")
    assert "CLIENT_OLLAMA_MODEL=qwen3.5:2b-q4_K_M" in installer_env
    assert "CLIENT_OLLAMA_MODEL_DIGEST=sha256:" + "9" * 64 in installer_env


def test_signed_package_canonicalizes_official_caddy_shorthand(package_inputs):
    packager, root, images, images_env, manifest, public_key, private_key, output, _ = package_inputs
    import verify_installer

    caddy_digest = "d" * 64
    images["CLIENT_CADDY_IMAGE"] = f"caddy@sha256:{caddy_digest}"
    images_env.write_text("".join(f"{key}={value}\n" for key, value in sorted(images.items())))

    packager.package_installer(images_env, manifest, public_key, private_key, output, root=root)

    with tarfile.open(output, "r:gz") as archive:
        env_example = archive.extractfile(".env.example")
        assert env_example is not None
        assert f"CLIENT_CADDY_IMAGE=docker.io/library/caddy@sha256:{caddy_digest}" in env_example.read().decode()
    assert verify_installer.verify_installer_archive(
        output, output.with_name(output.name + ".sig"), public_key
    ) == hashlib.sha256(output.read_bytes()).hexdigest()


def test_cloud_installer_ignores_blank_optional_model_pins(package_inputs):
    packager, _root, _images, images_env, manifest, public_key, private_key, output, signing_key = package_inputs
    images_env.write_text(
        images_env.read_text(encoding="utf-8")
        + "CLIENT_OLLAMA_IMAGE=\nCLIENT_INDIC_STT_IMAGE=\n"
        + "CLIENT_INDUS_TTS_IMAGE=\nCLIENT_INDIC_VITS_TTS_IMAGE=\n",
        encoding="utf-8",
    )
    signed = json.loads(manifest.read_text(encoding="utf-8"))
    signed["payload"]["model_images"] = {
        component: "ghcr.io/vendor/model@sha256:" + digest * 64
        for component, digest in zip(
            ("ollama", "indic_stt", "indus_tts", "indic_vits_tts"), "abcd", strict=True,
        )
    }
    canonical = json.dumps(signed["payload"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    signed["signature"] = base64.urlsafe_b64encode(signing_key.sign(canonical)).rstrip(b"=").decode("ascii")
    manifest.write_text(json.dumps(signed), encoding="utf-8")
    packager.package_installer(images_env, manifest, public_key, private_key, output, root=package_inputs[1])

    with tarfile.open(output, "r:gz") as archive:
        assert "docker-compose.models.yaml" not in archive.getnames()


def test_installer_rejects_model_digests_not_bound_into_manifest(package_inputs):
    packager, root, images, images_env, manifest, public_key, private_key, output, signing_key = package_inputs
    images.update({key: "ghcr.io/vendor/model@sha256:" + "d" * 64 for key in packager.MODEL_IMAGE_KEYS})
    images["CLIENT_OLLAMA_MODEL"] = "qwen3.5:2b-q4_K_M"
    images["CLIENT_OLLAMA_MODEL_DIGEST"] = "sha256:" + "9" * 64
    images_env.write_text("".join(f"{key}={value}\n" for key, value in sorted(images.items())))
    signed = json.loads(manifest.read_text(encoding="utf-8"))
    signed["payload"]["model_images"] = {
        component: "ghcr.io/vendor/model@sha256:" + "e" * 64
        for component in ("ollama", "indic_stt", "indus_tts", "indic_vits_tts")
    }
    signed["payload"]["model_assets"] = {
        "ollama": {"name": "qwen3.5:2b-q4_K_M", "digest": "sha256:" + "9" * 64},
    }
    canonical = json.dumps(signed["payload"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    signed["signature"] = base64.urlsafe_b64encode(signing_key.sign(canonical)).rstrip(b"=").decode("ascii")
    manifest.write_text(json.dumps(signed), encoding="utf-8")

    with pytest.raises(ValueError, match="do not match the installer image pins"):
        packager.package_installer(images_env, manifest, public_key, private_key, output, root=root)


def test_installer_rejects_unsigned_model_image_inventory(package_inputs):
    packager, root, images, images_env, manifest, public_key, private_key, output, _signing_key = package_inputs
    images.update({key: "ghcr.io/vendor/model@sha256:" + "d" * 64 for key in packager.MODEL_IMAGE_KEYS})
    images_env.write_text("".join(f"{key}={value}\n" for key, value in sorted(images.items())))

    with pytest.raises(ValueError, match="must sign the exact four configured local inference images"):
        packager.package_installer(images_env, manifest, public_key, private_key, output, root=root)


def test_installer_rejects_unapproved_object_storage_image(package_inputs):
    packager, root, images, images_env, manifest, public_key, private_key, output, _signing_key = package_inputs
    images["CLIENT_MINIO_IMAGE"] = "docker.io/minio/minio@sha256:" + "f" * 64
    images_env.write_text("".join(f"{key}={value}\n" for key, value in sorted(images.items())))

    with pytest.raises(ValueError, match="must use the approved PGSTY Silo object-storage image digest"):
        packager.package_installer(images_env, manifest, public_key, private_key, output, root=root)


def test_installer_rejects_silo_source_checksum_mismatch(package_inputs):
    packager, root, images, images_env, manifest, public_key, private_key, output, _signing_key = package_inputs
    source = root / "deploy/client/third-party" / packager.SILO_SOURCE_ARCHIVE_NAME
    source.write_bytes(b"tampered Silo source")

    with pytest.raises(ValueError, match="source archive does not match the approved release checksum"):
        packager.package_installer(images_env, manifest, public_key, private_key, output, root=root)


def test_disposable_ci_archive_keeps_storage_license_inventory(package_inputs):
    packager, root, images, images_env, manifest, public_key, private_key, output, _signing_key = package_inputs
    images["CLIENT_MINIO_IMAGE"] = "registry.example.com/kodewaves-ci/storage@sha256:" + "f" * 64
    images_env.write_text("".join(f"{key}={value}\n" for key, value in sorted(images.items())))
    source = root / "deploy/client/third-party" / packager.SILO_SOURCE_ARCHIVE_NAME

    packager.package_installer(
        images_env, manifest, public_key, private_key, output,
        root=root, silo_source_archive=source, allow_test_object_store=True,
    )

    with tarfile.open(output, "r:gz") as archive:
        assert packager.SILO_SOURCE_ARCHIVE_NAME in archive.getnames()
        assert "THIRD_PARTY_NOTICES.txt" in archive.getnames()


def test_installer_rejects_model_asset_name_mismatch(package_inputs):
    packager, root, images, images_env, manifest, public_key, private_key, output, signing_key = package_inputs
    images.update({key: "ghcr.io/vendor/model@sha256:" + "d" * 64 for key in packager.MODEL_IMAGE_KEYS})
    images["CLIENT_OLLAMA_MODEL"] = "qwen3.5:2b-q4_K_M"
    images["CLIENT_OLLAMA_MODEL_DIGEST"] = "sha256:" + "9" * 64
    images_env.write_text("".join(f"{key}={value}\n" for key, value in sorted(images.items())))
    signed = json.loads(manifest.read_text(encoding="utf-8"))
    signed["payload"]["model_images"] = {
        component: images[key]
        for component, key in (
            ("ollama", "CLIENT_OLLAMA_IMAGE"),
            ("indic_stt", "CLIENT_INDIC_STT_IMAGE"),
            ("indus_tts", "CLIENT_INDUS_TTS_IMAGE"),
            ("indic_vits_tts", "CLIENT_INDIC_VITS_TTS_IMAGE"),
        )
    }
    signed["payload"]["model_assets"] = {
        "ollama": {"name": "other-model:latest", "digest": "sha256:" + "9" * 64},
    }
    canonical = json.dumps(signed["payload"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    signed["signature"] = base64.urlsafe_b64encode(signing_key.sign(canonical)).rstrip(b"=").decode("ascii")
    manifest.write_text(json.dumps(signed), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match the installer model configuration"):
        packager.package_installer(images_env, manifest, public_key, private_key, output, root=root)


def test_installer_rejects_model_asset_digest_mismatch(package_inputs):
    packager, root, images, images_env, manifest, public_key, private_key, output, signing_key = package_inputs
    images.update({key: "ghcr.io/vendor/model@sha256:" + "d" * 64 for key in packager.MODEL_IMAGE_KEYS})
    images["CLIENT_OLLAMA_MODEL"] = "qwen3.5:2b-q4_K_M"
    images["CLIENT_OLLAMA_MODEL_DIGEST"] = "sha256:" + "8" * 64
    images_env.write_text("".join(f"{key}={value}\n" for key, value in sorted(images.items())))
    signed = json.loads(manifest.read_text(encoding="utf-8"))
    signed["payload"]["model_images"] = {
        component: images[key]
        for component, key in (
            ("ollama", "CLIENT_OLLAMA_IMAGE"),
            ("indic_stt", "CLIENT_INDIC_STT_IMAGE"),
            ("indus_tts", "CLIENT_INDUS_TTS_IMAGE"),
            ("indic_vits_tts", "CLIENT_INDIC_VITS_TTS_IMAGE"),
        )
    }
    signed["payload"]["model_assets"] = {
        "ollama": {"name": "qwen3.5:2b-q4_K_M", "digest": "sha256:" + "9" * 64},
    }
    canonical = json.dumps(signed["payload"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    signed["signature"] = base64.urlsafe_b64encode(signing_key.sign(canonical)).rstrip(b"=").decode("ascii")
    manifest.write_text(json.dumps(signed), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match the installer model configuration"):
        packager.package_installer(images_env, manifest, public_key, private_key, output, root=root)


def test_customer_archive_contains_only_installation_files_and_matching_images(package_inputs):
    packager, root, images, images_env, manifest, public_key, private_key, output, _ = package_inputs
    packager.package_installer(images_env, manifest, public_key, private_key, output, root=root)

    with tarfile.open(output, "r:gz") as archive:
        assert set(archive.getnames()) == {
            "README.md", "docker-compose.client.yaml", "docker-compose.identity.yaml", "docker-compose.recovery.yaml", "Caddyfile", "validate_install.py", "enroll_identity.py",
            "recovery.py", "compose_client.py", "recovery_lock.py", "verify_installer.py", "update_agent.py", "kodewaves-client-update.service", "kodewaves-client-update.timer", ".env.example", "client-release-manifest.json", "release-public-key.txt", "SHA256SUMS",
            "THIRD_PARTY_NOTICES.txt", "AGPL-3.0-PGSTY-Silo.txt", "PGSTY-Silo-NOTICE.txt", "PGSTY-Silo-CREDITS.txt", packager.SILO_SOURCE_ARCHIVE_NAME,
        }
        contents = {name: archive.extractfile(name).read() for name in archive.getnames()}
        assert archive.getmember(".env.example").mode == 0o600
    install_guide = contents["README.md"].decode("utf-8")
    assert "python3 compose_client.py pull api" in install_guide
    start_section = install_guide.split("## Start and create the administrator", 1)[1].split("## Renewal and recovery", 1)[0]
    compose_commands = [line.strip() for line in start_section.splitlines() if line.strip().startswith("python3 compose_client.py")]
    assert compose_commands
    assert all("compose_client.py" in command for command in compose_commands)
    assert b"customer-secret" not in b"".join(contents.values())
    assert b"private-key-must-never-ship" not in b"".join(contents.values())
    assert b"owner-signer-must-never-ship" not in b"".join(contents.values())
    assert b"GNU Affero General Public License" in contents["THIRD_PARTY_NOTICES.txt"]
    assert hashlib.sha256(contents[packager.SILO_SOURCE_ARCHIVE_NAME]).hexdigest() == packager.SILO_SOURCE_SHA256
    template = contents[".env.example"].decode("utf-8")
    for key, value in images.items():
        assert f"{key}={value}" in template
    assert contents["client-release-manifest.json"] == manifest.read_bytes()
    assert b"prepare_update_check" in contents["update_agent.py"]
    assert b"ExecStart=/usr/bin/python3 /opt/kodewaves/client/update_agent.py" in contents["kodewaves-client-update.service"]
    assert b"OnUnitActiveSec=15min" in contents["kodewaves-client-update.timer"]
    from verify_installer import verify_installer_archive
    assert verify_installer_archive(
        output, output.with_name(output.name + ".sig"), public_key
    ) == hashlib.sha256(output.read_bytes()).hexdigest()

    # The client updater consumes this exact owner-packaged archive format.
    # Exercise the package -> updater boundary, not a hand-built archive that
    # could drift away from the installer allowlist.
    import update_agent
    updater_extract = output.parent / "updater-extracted"
    release_manifest = update_agent._extract_verified_archive(output, updater_extract)
    assert release_manifest["payload"]["edition"] == "client"
    assert {path.name for path in updater_extract.iterdir()} == update_agent._PACKAGE_FILES

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
    recovery_help = subprocess.run(
        [sys.executable, "-I", "-S", "recovery.py", "--help"],
        cwd=extracted, capture_output=True, text=True, check=False,
    )
    assert recovery_help.returncode == 0, recovery_help.stderr
    assert "backup-docker" in recovery_help.stdout
    assert "rollback-docker" in recovery_help.stdout
    restore_help = subprocess.run(
        [sys.executable, "-I", "-S", "recovery.py", "restore", "--help"],
        cwd=extracted, capture_output=True, text=True, check=False,
    )
    assert restore_help.returncode == 0, restore_help.stderr
    assert "--docker-volumes" in restore_help.stdout
    assert "new offline directory" in recovery_help.stdout
    compose_help = subprocess.run(
        [sys.executable, "-I", "-S", "compose_client.py", "--help"],
        cwd=extracted, capture_output=True, text=True, check=False,
    )
    assert compose_help.returncode == 0, compose_help.stderr


def test_customer_archive_normalizes_windows_line_endings_for_attribution(package_inputs):
    packager, root, _images, images_env, manifest, public_key, private_key, output, _ = package_inputs
    third_party = root / "deploy/client/third-party"
    for name in ("AGPL-3.0-PGSTY-Silo.txt", "NOTICE", "CREDITS", "THIRD_PARTY_NOTICES.txt"):
        path = third_party / name
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))

    packager.package_installer(images_env, manifest, public_key, private_key, output, root=root)

    with tarfile.open(output, "r:gz") as archive:
        contents = {
            name: archive.extractfile(name).read()
            for name in (
                "AGPL-3.0-PGSTY-Silo.txt",
                "PGSTY-Silo-NOTICE.txt",
                "PGSTY-Silo-CREDITS.txt",
                "THIRD_PARTY_NOTICES.txt",
            )
        }
    assert all(b"\r\n" not in value for value in contents.values())
    assert hashlib.sha256(contents["AGPL-3.0-PGSTY-Silo.txt"]).hexdigest() == packager.SILO_LICENSE_SHA256
    assert hashlib.sha256(contents["PGSTY-Silo-NOTICE.txt"]).hexdigest() == packager.SILO_NOTICE_SHA256
    assert hashlib.sha256(contents["PGSTY-Silo-CREDITS.txt"]).hexdigest() == packager.SILO_CREDITS_SHA256

def test_customer_archive_is_reproducible_for_identical_release_inputs(package_inputs, monkeypatch):
    packager, root, _, images_env, manifest, public_key, private_key, output, _ = package_inputs
    second_output = output.with_name("installer-second.tar.gz")

    packager.package_installer(images_env, manifest, public_key, private_key, output, root=root)
    import gzip

    real_time = gzip.time.time
    monkeypatch.setattr(gzip.time, "time", lambda: real_time() + 10)
    packager.package_installer(images_env, manifest, public_key, private_key, second_output, root=root)

    assert output.read_bytes() == second_output.read_bytes()
    assert output.with_name(output.name + ".sig").read_bytes() == second_output.with_name(second_output.name + ".sig").read_bytes()


@pytest.mark.parametrize("problem", ["archive", "signature", "trusted_key"])
def test_customer_archive_detached_signature_rejects_tampering(package_inputs, tmp_path, problem):
    packager, root, _, images_env, manifest, public_key, private_key, output, _ = package_inputs
    packager.package_installer(images_env, manifest, public_key, private_key, output, root=root)
    signature = output.with_name(output.name + ".sig")
    archive_to_check = output
    signature_to_check = signature
    trusted_key = public_key
    if problem == "archive":
        archive_to_check = tmp_path / "modified.tar.gz"
        archive_to_check.write_bytes(output.read_bytes() + b"modified")
    elif problem == "signature":
        signature_to_check = tmp_path / "modified.sig"
        original = signature.read_text(encoding="ascii").strip()
        signature_to_check.write_text(("A" if original[0] != "A" else "B") + original[1:], encoding="ascii")
    else:
        wrong_private = Ed25519PrivateKey.generate()
        wrong_public = wrong_private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )
        trusted_key = tmp_path / "wrong-public.key"
        trusted_key.write_text(base64.urlsafe_b64encode(wrong_public).rstrip(b"=").decode("ascii"), encoding="ascii")

    from verify_installer import verify_installer_archive
    with pytest.raises(ValueError, match="signature is invalid"):
        verify_installer_archive(archive_to_check, signature_to_check, trusted_key)


@pytest.mark.parametrize("problem", ["signature", "image", "floating", "secret", "schema", "port", "private_key"])
def test_customer_archive_rejects_untrusted_or_unmatched_inputs_without_output(package_inputs, problem):
    packager, root, images, images_env, manifest, public_key, private_key, output, private = package_inputs
    private_key_to_use = private_key
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
    elif problem == "private_key":
        wrong_private = Ed25519PrivateKey.generate()
        private_key_to_use = output.with_name("wrong-release-private.key")
        private_key_to_use.write_bytes(wrong_private.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        ))
        error = "does not match the trusted public key"
    else:
        signed = json.loads(manifest.read_text())
        signed["payload"].pop("schema_compatibility")
        signature = private.sign(json.dumps(signed["payload"], sort_keys=True, separators=(",", ":")).encode("utf-8"))
        signed["signature"] = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
        manifest.write_text(json.dumps(signed))
        error = "signed schema compatibility metadata"

    with pytest.raises(ValueError, match=error):
        packager.package_installer(images_env, manifest, public_key, private_key_to_use, output, root=root)
    assert not output.exists()


def test_customer_archive_never_overwrites_an_existing_delivery(package_inputs):
    packager, root, _, images_env, manifest, public_key, private_key, output, _ = package_inputs
    output.write_bytes(b"existing-approved-delivery")
    with pytest.raises(ValueError, match="already exists"):
        packager.package_installer(images_env, manifest, public_key, private_key, output, root=root)
    assert output.read_bytes() == b"existing-approved-delivery"
