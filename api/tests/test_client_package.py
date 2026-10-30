import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def test_client_compose_has_no_source_build_or_runtime_checkout_mount():
    path = Path(__file__).resolve().parents[2] / "deploy/client/docker-compose.client.yaml"
    stack = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert {"api", "ui", "postgres", "redis", "minio", "coturn", "caddy"} <= set(stack["services"])
    for name, service in stack["services"].items():
        assert "build" not in service, f"{name} cannot build from customer source"
        for mount in service.get("volumes", []):
            assert not str(mount).startswith("../"), f"{name} mounts outside the client package: {mount}"
            if str(mount).startswith("./"):
                assert name == "caddy" and mount == "./Caddyfile:/etc/caddy/Caddyfile:ro"
    api = stack["services"]["api"]
    ui = stack["services"]["ui"]
    for name, service in (("api", api), ("ui", ui)):
        assert service["read_only"] is True, f"{name} source filesystem must be immutable at runtime"
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        assert any(str(item).startswith("/tmp:") for item in service["tmpfs"])
    assert api["environment"]["KODEWAVES_EDITION"] == "client"
    assert api["environment"]["KODEWAVES_RELEASE_MANIFEST"] == "/app/client-release-manifest.json"
    assert api["environment"]["KODEWAVES_API_IMAGE"] == "${CLIENT_API_IMAGE:?Set pinned client API image digest}"
    assert api["environment"]["KODEWAVES_UI_IMAGE"] == "${CLIENT_UI_IMAGE:?Set pinned client UI image digest}"
    assert "KODEWAVES_LICENSE_PUBLIC_KEY" not in api["environment"]
    assert "KODEWAVES_RELEASE_PUBLIC_KEY" not in api["environment"]
    assert "KODEWAVES_OWNER_STATUS_URL" not in api["environment"]
    assert ui["environment"]["KODEWAVES_EDITION"] == "client"
    assert ui["environment"]["KODEWAVES_RELEASE_MANIFEST"] == "/app/client-release-manifest.json"
    assert ui["environment"]["KODEWAVES_API_IMAGE"] == "${CLIENT_API_IMAGE:?Set pinned client API image digest}"
    assert ui["environment"]["KODEWAVES_UI_IMAGE"] == "${CLIENT_UI_IMAGE:?Set pinned client UI image digest}"
    assert "KODEWAVES_LICENSE_TOKEN" in ui["environment"]
    assert any("/app/client-release-manifest.json:ro" in str(mount) for mount in ui["volumes"])
    assert any(str(item).startswith("/app/.next/cache:") for item in ui["tmpfs"])
    assert any(str(item).endswith(":/app/kodewaves_pcm_cache") for item in api["volumes"])
    assert "api_audio_cache" in stack["volumes"]
    assert api["environment"]["ENABLE_SIGNUP"] == "false"


def test_identity_overlay_mounts_only_the_read_only_key_for_api_and_ui():
    root = Path(__file__).resolve().parents[2]
    overlay = yaml.safe_load((root / "deploy/client/docker-compose.identity.yaml").read_text())
    assert set(overlay["services"]) == {"api", "ui"}
    for service in overlay["services"].values():
        assert service["environment"]["KODEWAVES_INSTALLATION_KEY_FILE"] == "/run/kodewaves-identity/installation.key"
        assert service["group_add"] == ["${CLIENT_IDENTITY_GID:?Set the key file's numeric read-only group}"]
        mount = service["volumes"][0]
        assert mount["source"].startswith("${CLIENT_IDENTITY_KEY_FILE:?")
        assert mount["read_only"] is True
        assert mount["bind"]["create_host_path"] is False


def test_identity_preflight_requires_an_existing_private_key_and_group(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "deploy/client"))
    import validate_install

    path = tmp_path / "installation.key"
    path.write_bytes(b"x" * 32)
    assert validate_install.validate_identity_key({}) == []
    assert validate_install.validate_identity_key({"CLIENT_IDENTITY_KEY_FILE": str(path)})
    assert validate_install.validate_identity_key({"CLIENT_IDENTITY_KEY_FILE": str(path), "CLIENT_IDENTITY_GID": "0"})
    if os.name == "nt":
        group = "10003"
    else:
        group = str(path.stat().st_gid)
        if group == "0":
            os.chown(path, -1, 10003)
            group = "10003"
        path.chmod(0o640)
    values = {"CLIENT_IDENTITY_KEY_FILE": str(path), "CLIENT_IDENTITY_GID": group}
    assert validate_install.validate_identity_key(values) == []
    if os.name != "nt":
        path.chmod(0o440)
        assert any("0640" in error for error in validate_install.validate_identity_key(values))
        path.chmod(0o740)
        assert any("0640" in error for error in validate_install.validate_identity_key(values))
        path.chmod(0o644)
        assert any("inaccessible to others" in error for error in validate_install.validate_identity_key(values))
    path.write_bytes(b"short")
    assert any("32-byte" in error for error in validate_install.validate_identity_key({
        "CLIENT_IDENTITY_KEY_FILE": str(path), "CLIENT_IDENTITY_GID": "10003",
    }))


def test_client_compose_waits_for_healthy_stateful_and_upstream_services():
    path = Path(__file__).resolve().parents[2] / "deploy/client/docker-compose.client.yaml"
    services = yaml.safe_load(path.read_text(encoding="utf-8"))["services"]

    for name in ("postgres", "redis", "minio"):
        assert services[name].get("healthcheck"), f"{name} needs a startup health check"

    assert services["api"]["depends_on"] == {
        "postgres": {"condition": "service_healthy"},
        "redis": {"condition": "service_healthy"},
        "minio": {"condition": "service_healthy"},
    }
    assert services["ui"]["depends_on"] == {
        "api": {"condition": "service_healthy"},
    }
    # Ingress must start even when a component fails its startup checks.
    assert not services["caddy"].get("depends_on")


def test_client_docker_entrypoint_keeps_one_reachable_fastapi_listener():
    root = Path(__file__).resolve().parents[2]
    script = (root / "scripts/start_services_docker.sh").read_text(encoding="utf-8")
    client_branch = script.split('if [[ "${KODEWAVES_EDITION:-saas}" == "client" ]]; then', 1)[1]
    client_branch = client_branch.split("elif [[", 1)[0]
    assert "FASTAPI_WORKERS=1" in client_branch
    assert 'FASTAPI_WORKERS: "1"' in (root / "deploy/client/docker-compose.client.yaml").read_text(encoding="utf-8")


def test_owner_only_database_modules_are_removed_and_checked_at_release():
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "api/Dockerfile").read_text()
    verifier = (root / "deploy/client/verify_images.py").read_text()
    for module in ("owner_user_management", "saas_plan_catalog"):
        path = f"api/db/{module}.py"
        assert f"./{path}" in dockerfile
        assert repr(path) in verifier
    assert "./scripts/create_superuser.py" in dockerfile
    assert "'scripts/create_superuser.py'" in verifier
    assert "COPY --from=api-source --chown=kodewaves:kodewaves /app/scripts ./scripts" in dockerfile


def test_client_direct_ingress_routes_api_audio_and_ui_by_path():
    root = Path(__file__).resolve().parents[2]
    stack = yaml.safe_load((root / "deploy/client/docker-compose.client.yaml").read_text())
    ingress = stack["services"]["caddy"]
    api = stack["services"]["api"]
    assert "direct-ingress" in ingress["profiles"]
    assert {"80:80", "443:443", "443:443/udp"} <= set(ingress["ports"])
    assert api["environment"]["FORWARDED_ALLOW_IPS"] == "${FORWARDED_ALLOW_IPS:-${CLIENT_CADDY_IPV4:-172.30.0.2}}"
    assert ingress["networks"]["internal"]["ipv4_address"] == "${CLIENT_CADDY_IPV4:-172.30.0.2}"
    assert stack["networks"]["internal"]["ipam"]["config"][0]["subnet"] == "${CLIENT_INTERNAL_SUBNET:-172.30.0.0/24}"
    caddyfile = (root / "deploy/client/Caddyfile").read_text()
    assert "@api path /api/v1 /api/v1/*" in caddyfile
    assert "reverse_proxy api:8000" in caddyfile
    assert "@audio path /voice-audio /voice-audio/*" in caddyfile
    assert "reverse_proxy minio:9000" in caddyfile
    assert "reverse_proxy ui:3010" in caddyfile
    assert "handle_errors" in caddyfile
    assert "Service temporarily unavailable" in caddyfile
    assert 'Cache-Control "no-store"' in caddyfile
    assert "header_up Host {host}" in caddyfile
    assert "admin off" in caddyfile
    install_readme = (root / "deploy/client/README.md").read_text()
    assert "@api path /api/v1 /api/v1/*" in install_readme
    assert "reverse_proxy 127.0.0.1:8000" in install_readme
    assert "@audio path /voice-audio /voice-audio/*" in install_readme
    assert "reverse_proxy 127.0.0.1:9000" in install_readme
    assert "reverse_proxy 127.0.0.1:3010" in install_readme
    assert "Expose the configured TURN UDP/TCP ports directly" in install_readme
    assert "FORWARDED_ALLOW_IPS" in install_readme
    assert "Do not use `*`" in install_readme
    example_env = (root / "deploy/client/.env.example").read_text()
    assert "COMPOSE_PROFILES=direct-ingress" in example_env
    assert "CLIENT_CADDY_IMAGE=" in example_env


def test_client_caddy_image_is_required_only_when_direct_ingress_is_enabled(tmp_path):
    client_dir = Path(__file__).resolve().parents[2] / "deploy/client"
    sys.path.insert(0, str(client_dir))
    try:
        import validate_install
    finally:
        sys.path.remove(str(client_dir))

    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n  caddy:\n    image: ${CLIENT_CADDY_IMAGE:-registry.invalid/kodewaves-caddy-disabled@sha256:"
        + "0" * 64 + "}\n",
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text("COMPOSE_PROFILES=\nFORWARDED_ALLOW_IPS=172.30.0.1\n", encoding="utf-8")
    assert validate_install.validate(env_file, compose)[0].startswith("preflight passed;")

    env_file.write_text("COMPOSE_PROFILES=direct-ingress\nFORWARDED_ALLOW_IPS=172.30.0.2\n", encoding="utf-8")
    errors = validate_install.validate(env_file, compose)
    assert any("CLIENT_CADDY_IMAGE is required" in error for error in errors)


def test_client_compose_uses_fail_closed_caddy_image_fallback():
    path = Path(__file__).resolve().parents[2] / "deploy/client/docker-compose.client.yaml"
    stack = yaml.safe_load(path.read_text(encoding="utf-8"))
    caddy_image = stack["services"]["caddy"]["image"]
    assert caddy_image.startswith("${CLIENT_CADDY_IMAGE:-")
    assert "@sha256:" in caddy_image


def test_client_environment_template_covers_required_compose_values():
    root = Path(__file__).resolve().parents[2]
    compose = (root / "deploy/client/docker-compose.client.yaml").read_text(encoding="utf-8")
    template = (root / "deploy/client/.env.example").read_text(encoding="utf-8")
    required = set(re.findall(r"\$\{([A-Z0-9_]+):\?", compose))
    configured = set(re.findall(r"^([A-Z0-9_]+)=", template, flags=re.MULTILINE))
    assert required <= configured


def test_client_install_preflight_accepts_valid_inputs_and_rejects_common_mistakes(tmp_path):
    root = Path(__file__).resolve().parents[2]
    client_dir = root / "deploy/client"
    sys.path.insert(0, str(client_dir))
    try:
        import validate_install
    finally:
        sys.path.remove(str(client_dir))

    manifest = tmp_path / "client-release-manifest.json"
    manifest.write_text(json.dumps({"payload": {}}), encoding="utf-8")
    lines = [
        f"{key}=registry.example.com/kodewaves/{key.lower()}@sha256:{'a' * 64}"
        for key in sorted(validate_install.IMAGE_KEYS)
    ]
    lines += [
        "COMPOSE_PROFILES=direct-ingress",
        "CLIENT_INTERNAL_SUBNET=172.30.0.0/24",
        "CLIENT_CADDY_IPV4=172.30.0.2",
        "FORWARDED_ALLOW_IPS=172.30.0.2",
        "CLIENT_RELEASE_MANIFEST_FILE=client-release-manifest.json",
        "KODEWAVES_INSTALLATION_ID=installation-123",
        "KODEWAVES_LICENSE_TOKEN=payload.signature",
        "PUBLIC_HOST=voice.customer.example.com",
        "TURN_HOST=8.8.8.8",
        "MINIO_ROOT_USER=kodewaves-storage",
        "MASTER_CREDENTIAL_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("="),
    ]
    lines.extend(f"{key}={'s' * 40}" for key in validate_install.SECRET_KEYS)
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = validate_install.validate(env_file, client_dir / "docker-compose.client.yaml")
    assert result == ["preflight passed; run docker compose config --quiet for Compose validation and API startup to verify signed license and manifest"]

    api_ref = next(line.split("=", 1)[1] for line in lines if line.startswith("CLIENT_API_IMAGE="))
    ui_ref = next(line.split("=", 1)[1] for line in lines if line.startswith("CLIENT_UI_IMAGE="))
    manifest.write_text(json.dumps({"payload": {"images": {
        "api": {"kind": "registry_digest", "reference": api_ref},
        "ui": {"kind": "registry_digest", "reference": ui_ref},
    }}}), encoding="utf-8")
    assert validate_install.validate(env_file, client_dir / "docker-compose.client.yaml")[0].startswith("preflight passed;")
    manifest.write_text(json.dumps({"payload": {"images": {
        "api": {"kind": "registry_digest", "reference": api_ref},
    }}}), encoding="utf-8")
    assert any("manifest must contain API and UI image entries" in error for error in validate_install.validate(
        env_file, client_dir / "docker-compose.client.yaml"
    ))
    manifest.write_text(json.dumps({"payload": {"images": {}}}), encoding="utf-8")
    assert any("manifest must contain API and UI image entries" in error for error in validate_install.validate(
        env_file, client_dir / "docker-compose.client.yaml"
    ))
    manifest.write_text(json.dumps({"payload": {"images": {
        "api": None,
        "ui": {"kind": "registry_digest", "reference": ui_ref},
    }}}), encoding="utf-8")
    assert any("CLIENT_API_IMAGE does not match" in error for error in validate_install.validate(
        env_file, client_dir / "docker-compose.client.yaml"
    ))
    manifest.write_text(json.dumps({"payload": []}), encoding="utf-8")
    assert any("manifest must contain a payload object" in error for error in validate_install.validate(
        env_file, client_dir / "docker-compose.client.yaml"
    ))
    manifest.write_text(json.dumps({"payload": {"images": {
        "api": {"kind": "registry_digest", "reference": api_ref[:-1] + "b"},
        "ui": {"kind": "registry_digest", "reference": ui_ref},
    }}}), encoding="utf-8")
    assert any("CLIENT_API_IMAGE does not match" in error for error in validate_install.validate(
        env_file, client_dir / "docker-compose.client.yaml"
    ))
    manifest.write_text(json.dumps({"payload": {}}), encoding="utf-8")

    for extra, expected in [
        (["API_PORT=0"], "API_PORT"),
        (["UI_PORT=65536"], "UI_PORT"),
        (["MINIO_PORT=invalid"], "MINIO_PORT"),
        (["UI_PORT=8000"], "distinct"),
    ]:
        env_file.write_text("\n".join(lines + extra) + "\n", encoding="utf-8")
        assert any(expected in error for error in validate_install.validate(env_file, client_dir / "docker-compose.client.yaml"))
    for length, valid in ((100, True), (101, False)):
        identity_lines = [f"KODEWAVES_INSTALLATION_ID={'a' * length}" if line.startswith("KODEWAVES_INSTALLATION_ID=") else line for line in lines]
        env_file.write_text("\n".join(identity_lines) + "\n", encoding="utf-8")
        errors = validate_install.validate(env_file, client_dir / "docker-compose.client.yaml")
        assert any("KODEWAVES_INSTALLATION_ID" in error for error in errors) is not valid
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # The real Compose file must also accept an external-proxy deployment with
    # no Caddy image, not just a reduced fixture containing the Caddy service.
    external_proxy_lines = [
        "COMPOSE_PROFILES=" if line == "COMPOSE_PROFILES=direct-ingress"
        else "FORWARDED_ALLOW_IPS=172.30.0.1" if line == "FORWARDED_ALLOW_IPS=172.30.0.2"
        else line for line in lines
        if not line.startswith("CLIENT_CADDY_IMAGE=")
    ]
    external_proxy_env = tmp_path / "external-proxy.env"
    external_proxy_env.write_text("\n".join(external_proxy_lines) + "\n", encoding="utf-8")
    assert validate_install.validate(
        external_proxy_env, client_dir / "docker-compose.client.yaml"
    ) == ["preflight passed; run docker compose config --quiet for Compose validation and API startup to verify signed license and manifest"]

    invalid_lines = [line.replace("@sha256:" + "a" * 64, ":latest") if line.startswith("CLIENT_API_IMAGE=") else line for line in lines]
    invalid_lines = [line.replace("POSTGRES_PASSWORD=" + "s" * 40, "POSTGRES_PASSWORD=bad@password") for line in invalid_lines]
    invalid_lines = [line.replace("TURN_HOST=8.8.8.8", "TURN_HOST=https://turn.example.com") for line in invalid_lines]
    invalid_file = tmp_path / "invalid.env"
    invalid_file.write_text("\n".join(invalid_lines) + "\n", encoding="utf-8")
    errors = validate_install.validate(invalid_file, client_dir / "docker-compose.client.yaml")
    assert any("CLIENT_API_IMAGE" in error and "pinned" in error for error in errors)
    assert any("POSTGRES_PASSWORD" in error and "URL-safe" in error for error in errors)
    assert any("TURN_HOST" in error and "IPv4" in error for error in errors)

    invalid_port_lines = [
        line.replace("registry.example.com/", "registry.example.com:99999/")
        if line.startswith("CLIENT_API_IMAGE=") else line
        for line in lines
    ]
    invalid_port_file = tmp_path / "invalid-registry-port.env"
    invalid_port_file.write_text("\n".join(invalid_port_lines) + "\n", encoding="utf-8")
    port_errors = validate_install.validate(invalid_port_file, client_dir / "docker-compose.client.yaml")
    assert any("CLIENT_API_IMAGE registry port must be between 1 and 65535" in error for error in port_errors)


def test_client_install_preflight_rejects_untrusted_or_insecure_forwarded_proxy_config(tmp_path):
    root = Path(__file__).resolve().parents[2]
    client_dir = root / "deploy/client"
    sys.path.insert(0, str(client_dir))
    try:
        import validate_install
    finally:
        sys.path.remove(str(client_dir))

    manifest = tmp_path / "client-release-manifest.json"
    manifest.write_text(json.dumps({"payload": {}}), encoding="utf-8")
    lines = [
        f"{key}=registry.example.com/kodewaves/{key.lower()}@sha256:{'a' * 64}"
        for key in sorted(validate_install.IMAGE_KEYS)
    ]
    lines += [
        "COMPOSE_PROFILES=direct-ingress",
        "CLIENT_INTERNAL_SUBNET=172.30.0.0/24",
        "CLIENT_CADDY_IPV4=172.30.0.2",
        "FORWARDED_ALLOW_IPS=*",
        "CLIENT_RELEASE_MANIFEST_FILE=client-release-manifest.json",
        "KODEWAVES_INSTALLATION_ID=installation-123",
        "KODEWAVES_LICENSE_TOKEN=payload.signature",
        "PUBLIC_HOST=voice.customer.example.com",
        "TURN_HOST=8.8.8.8",
        "MINIO_ROOT_USER=kodewaves-storage",
        "MASTER_CREDENTIAL_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("="),
    ]
    lines.extend(f"{key}={'s' * 40}" for key in validate_install.SECRET_KEYS)
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    errors = validate_install.validate(env_file, client_dir / "docker-compose.client.yaml")
    assert any("FORWARDED_ALLOW_IPS" in error and "wildcard" in error for error in errors)

    lines[lines.index("FORWARDED_ALLOW_IPS=*")] = "FORWARDED_ALLOW_IPS=172.30.0.1"
    lines[lines.index("CLIENT_CADDY_IPV4=172.30.0.2")] = "CLIENT_CADDY_IPV4=172.30.1.2"
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    errors = validate_install.validate(env_file, client_dir / "docker-compose.client.yaml")
    assert any("CLIENT_CADDY_IPV4" in error and "inside CLIENT_INTERNAL_SUBNET" in error for error in errors)

    interpolation_lines = [
        line.replace("CLIENT_API_IMAGE=", "CLIENT_API_IMAGE=registry.example.com/${INJECTED}/")
        for line in lines
    ]
    interpolation_file = tmp_path / "interpolation.env"
    interpolation_file.write_text("\n".join(interpolation_lines) + "\n", encoding="utf-8")
    interpolation_errors = validate_install.validate(
        interpolation_file, client_dir / "docker-compose.client.yaml"
    )
    assert any("CLIENT_API_IMAGE" in error and "pinned" in error for error in interpolation_errors)


def test_client_install_preflight_runs_without_third_party_python_packages(tmp_path):
    root = Path(__file__).resolve().parents[2]
    client_dir = root / "deploy/client"
    compose = client_dir / "docker-compose.client.yaml"
    manifest = tmp_path / "client-release-manifest.json"
    manifest.write_text(json.dumps({"payload": {}}), encoding="utf-8")
    lines = [
        f"{key}=registry.example.com/kodewaves/{key.lower()}@sha256:{'e' * 64}"
        for key in (
            "CLIENT_API_IMAGE", "CLIENT_UI_IMAGE", "CLIENT_POSTGRES_IMAGE",
            "CLIENT_REDIS_IMAGE", "CLIENT_MINIO_IMAGE", "CLIENT_COTURN_IMAGE",
            "CLIENT_CADDY_IMAGE",
        )
    ]
    lines += [
        "COMPOSE_PROFILES=direct-ingress",
        "CLIENT_RELEASE_MANIFEST_FILE=client-release-manifest.json",
        "KODEWAVES_INSTALLATION_ID=installation-123",
        "KODEWAVES_LICENSE_TOKEN=payload.signature",
        "PUBLIC_HOST=voice.customer.example.com",
        "TURN_HOST=8.8.8.8",
        "MINIO_ROOT_USER=kodewaves-storage",
        "MASTER_CREDENTIAL_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(b"e" * 32).decode().rstrip("="),
    ]
    for key in ("POSTGRES_PASSWORD", "REDIS_PASSWORD", "MINIO_ROOT_PASSWORD", "OSS_JWT_SECRET", "TELEPHONY_WS_TOKEN_SECRET", "TURN_SECRET"):
        lines.append(f"{key}={'s' * 40}")
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-S", str(client_dir / "validate_install.py"),
         "--env-file", str(env_file), "--compose-file", str(compose)],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Client installation inputs look valid" in result.stdout


def test_client_install_preflight_rejects_missing_manifest_and_template_values(tmp_path):
    root = Path(__file__).resolve().parents[2]
    client_dir = root / "deploy/client"
    sys.path.insert(0, str(client_dir))
    try:
        import validate_install
    finally:
        sys.path.remove(str(client_dir))

    env_file = tmp_path / ".env"
    env_file.write_text(
        "CLIENT_API_IMAGE=registry.example.com/kodewaves/api@sha256:" + "a" * 64 + "\n"
        "CLIENT_RELEASE_MANIFEST_FILE=missing.json\n"
        "PUBLIC_HOST=voice.customer.example.com\n"
        "KODEWAVES_LICENSE_TOKEN=<owner-signed-license-token>\n",
        encoding="utf-8",
    )
    errors = validate_install.validate(env_file, client_dir / "docker-compose.client.yaml")
    assert any("CLIENT_UI_IMAGE is required" in error for error in errors)
    assert any("KODEWAVES_LICENSE_TOKEN still contains" in error for error in errors)
    assert any("signed release manifest does not exist" in error for error in errors)


def test_client_install_preflight_rejects_ipv6_turn_and_bad_license_and_server_ip(tmp_path):
    root = Path(__file__).resolve().parents[2]
    client_dir = root / "deploy/client"
    sys.path.insert(0, str(client_dir))
    try:
        import validate_install
    finally:
        sys.path.remove(str(client_dir))

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"payload": {}}), encoding="utf-8")
    lines = [f"{key}=registry.example.com/kodewaves/{key.lower()}@sha256:{'b' * 64}" for key in sorted(validate_install.IMAGE_KEYS)]
    lines += [
        "COMPOSE_PROFILES=",
        "CLIENT_RELEASE_MANIFEST_FILE=manifest.json",
        "KODEWAVES_INSTALLATION_ID=installation-123",
        "KODEWAVES_LICENSE_TOKEN=malformed",
        "PUBLIC_HOST=voice.customer.example.com",
        "TURN_HOST=2001:4860:4860::8888",
        "SERVER_IP=not-an-ip",
        "MINIO_ROOT_USER=kodewaves-storage",
        "MASTER_CREDENTIAL_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(b"z" * 32).decode().rstrip("="),
    ]
    lines.extend(f"{key}={'x' * 40}" for key in validate_install.SECRET_KEYS)
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    errors = validate_install.validate(env_file, client_dir / "docker-compose.client.yaml")
    assert any("KODEWAVES_LICENSE_TOKEN" in error and "payload.signature" in error for error in errors)
    assert any("SERVER_IP" in error for error in errors)
    assert any("TURN_HOST" in error and "IPv6" in error for error in errors)
    assert not any("CLIENT_CADDY_IMAGE" in error for error in errors)


@pytest.mark.parametrize(
    "key",
    [
        "!" + base64.urlsafe_b64encode(b"q" * 32).decode().rstrip("="),
        base64.urlsafe_b64encode(b"q" * 32).decode().rstrip("=") + "!",
        base64.urlsafe_b64encode(b"\xff" * 32).decode().replace("_", "/").rstrip("="),
        "=" + base64.urlsafe_b64encode(b"q" * 32).decode().rstrip("="),
    ],
)
def test_client_install_preflight_rejects_malformed_credential_encryption_key(tmp_path, key):
    root = Path(__file__).resolve().parents[2]
    client_dir = root / "deploy/client"
    sys.path.insert(0, str(client_dir))
    try:
        import validate_install
    finally:
        sys.path.remove(str(client_dir))

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"payload": {}}), encoding="utf-8")
    lines = [
        f"{name}=registry.example.com/kodewaves/{name.lower()}@sha256:{'f' * 64}"
        for name in sorted(validate_install.IMAGE_KEYS)
    ]
    lines.extend(
        [
            "COMPOSE_PROFILES=direct-ingress",
            "CLIENT_RELEASE_MANIFEST_FILE=manifest.json",
            "KODEWAVES_INSTALLATION_ID=installation-123",
            "KODEWAVES_LICENSE_TOKEN=payload.signature",
            "PUBLIC_HOST=voice.customer.example.com",
            "TURN_HOST=8.8.4.4",
            f"MASTER_CREDENTIAL_ENCRYPTION_KEY={key}",
        ]
    )
    lines.extend(f"{name}={'r' * 40}" for name in validate_install.SECRET_KEYS)
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    errors = validate_install.validate(env_file, client_dir / "docker-compose.client.yaml")
    assert any("MASTER_CREDENTIAL_ENCRYPTION_KEY" in error for error in errors)


@pytest.mark.parametrize("host", ["voice.example.com,evil.example.com", "voice.example.com { respond 200", "https://voice.example.com", "voice.example.com:443"])
def test_client_install_preflight_rejects_non_dns_caddy_host_values(tmp_path, host):
    root = Path(__file__).resolve().parents[2]
    client_dir = root / "deploy/client"
    sys.path.insert(0, str(client_dir))
    try:
        import validate_install
    finally:
        sys.path.remove(str(client_dir))

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"payload": {}}), encoding="utf-8")
    lines = [f"{key}=registry.example.com/kodewaves/{key.lower()}@sha256:{'c' * 64}" for key in sorted(validate_install.IMAGE_KEYS)]
    lines += [
        "COMPOSE_PROFILES=direct-ingress",
        "CLIENT_RELEASE_MANIFEST_FILE=manifest.json",
        "KODEWAVES_INSTALLATION_ID=installation-123",
        "KODEWAVES_LICENSE_TOKEN=payload.signature",
        f"PUBLIC_HOST={host}",
        "TURN_HOST=1.1.1.1",
        "MINIO_ROOT_USER=kodewaves-storage",
        "MASTER_CREDENTIAL_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(b"m" * 32).decode().rstrip("="),
    ]
    lines.extend(f"{key}={'z' * 40}" for key in validate_install.SECRET_KEYS)
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    errors = validate_install.validate(env_file, client_dir / "docker-compose.client.yaml")
    assert any("PUBLIC_HOST" in error for error in errors)


def test_client_install_preflight_accepts_idn_hostname_normalized_for_license(tmp_path):
    root = Path(__file__).resolve().parents[2]
    client_dir = root / "deploy/client"
    sys.path.insert(0, str(client_dir))
    try:
        import validate_install
    finally:
        sys.path.remove(str(client_dir))

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"payload": {}}), encoding="utf-8")
    lines = [f"{key}=registry.example.com/kodewaves/{key.lower()}@sha256:{'d' * 64}" for key in sorted(validate_install.IMAGE_KEYS)]
    lines += [
        "COMPOSE_PROFILES=direct-ingress",
        "CLIENT_RELEASE_MANIFEST_FILE=manifest.json",
        "KODEWAVES_INSTALLATION_ID=installation-123",
        "KODEWAVES_LICENSE_TOKEN=payload.signature",
        "PUBLIC_HOST=ग्राहक.example",
        "TURN_HOST=9.9.9.9",
        "MINIO_ROOT_USER=kodewaves-storage",
        "MASTER_CREDENTIAL_ENCRYPTION_KEY=" + base64.urlsafe_b64encode(b"n" * 32).decode().rstrip("="),
    ]
    lines.extend(f"{key}={'y' * 40}" for key in validate_install.SECRET_KEYS)
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = validate_install.validate(env_file, client_dir / "docker-compose.client.yaml")
    assert result[0].startswith("preflight passed;")


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.20.30.40", "192.168.1.20", "169.254.1.2", "192.0.2.5", "2001:db8::5"],
)
def test_client_install_preflight_rejects_non_public_turn_address(tmp_path, address):
    root = Path(__file__).resolve().parents[2]
    client_dir = root / "deploy/client"
    sys.path.insert(0, str(client_dir))
    try:
        import validate_install
    finally:
        sys.path.remove(str(client_dir))

    env_file = tmp_path / ".env"
    env_file.write_text(f"TURN_HOST={address}\n", encoding="utf-8")
    errors = validate_install.validate(env_file, client_dir / "docker-compose.client.yaml")
    assert any("TURN_HOST must be a globally routable" in error for error in errors)


def test_client_install_readme_runs_preflight_before_compose():
    root = Path(__file__).resolve().parents[2]
    readme = (root / "deploy/client/README.md").read_text(encoding="utf-8")
    assert "python3 validate_install.py" in readme
    assert readme.index("python3 validate_install.py") < readme.index(
        "python3 compose_client.py up -d api"
    )
    assert "reruns the local preflight" in readme


def test_release_builder_rejects_unknown_upgrade_origin_before_docker(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "deploy/client"))
    import build_and_verify

    monkeypatch.setattr(build_and_verify.subprocess, "run", lambda *args, **kwargs: pytest.fail("Docker must not run"))
    monkeypatch.setattr(sys, "argv", [
        "build_and_verify.py", "--caddy-image", "registry.example.com/caddy@sha256:" + "a" * 64,
        "--license-public-key-file", str(tmp_path / "license.pub"),
        "--release-public-key-file", str(tmp_path / "release.pub"),
        "--owner-status-url", "https://owner.example.com/check",
        "--owner-private-key", str(tmp_path / "release.key"),
        "--manifest-output", str(tmp_path / "manifest.json"),
        "--public-key-output", str(tmp_path / "output.pub"),
        "--approved-upgrade-from", "unknown_revision",
    ])
    with pytest.raises(ValueError, match="not ancestors"):
        build_and_verify.main()


def test_api_image_verifier_requires_the_signed_runtime_docs_index(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "deploy/client"))
    import verify_images

    commands = []
    monkeypatch.setattr(verify_images, "_run", lambda *args: commands.append(args) or "verified")
    verify_images.verify_api("client-api:test")

    code = commands[0][-1]
    assert "docs/docs.json" in code
    assert "api/services/release_schema.py" in code


def test_release_verifier_checks_caddyfile_with_the_approved_digest(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "deploy/client"))
    import verify_images

    calls = []
    monkeypatch.setattr(
        verify_images.subprocess,
        "run",
        lambda args, **kwargs: calls.append((args, kwargs)) or SimpleNamespace(stdout="Valid configuration"),
    )
    image = "registry.example.com/kodewaves/caddy@sha256:" + "d" * 64
    verify_images.verify_caddyfile(image, str(root / "deploy/client/Caddyfile"))
    command = calls[0][0]
    assert list(command[:5]) == ["docker", "run", "--rm", "--network", "none"]
    assert list(command[-5:]) == [
        "validate", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile",
    ]
    with pytest.raises(ValueError, match="immutable sha256 digest"):
        verify_images.verify_caddyfile("caddy:latest", str(root / "deploy/client/Caddyfile"))


@pytest.mark.parametrize("shared_repository", [False, True])
def test_release_publisher_stages_unique_refs_without_touching_release_tags(monkeypatch, shared_repository):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "deploy/client"))
    import build_and_verify

    api_repository = "registry.example.com/kodewaves/api"
    ui_repository = api_repository if shared_repository else "registry.example.com/kodewaves/ui"
    api_digest = api_repository + "@sha256:" + "a" * 64
    ui_digest = ui_repository + "@sha256:" + "b" * 64
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[1] in {"tag", "push"}:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        digest = api_digest if command[-1].endswith("-api") else ui_digest
        return SimpleNamespace(stdout=json.dumps([digest]))

    monkeypatch.setattr(build_and_verify.subprocess, "run", run)
    staging, pinned = build_and_verify.push_staging_images(
        "local-api:built", "local-ui:built",
        api_repository + ":api-release",
        ui_repository + ":ui-release",
        release_id="abc123",
    )

    assert staging == (
        api_repository + ":kodewaves-verify-abc123-api",
        ui_repository + ":kodewaves-verify-abc123-ui",
    )
    assert pinned == (api_digest, ui_digest)
    assert [command[1] for command in calls] == ["tag", "push", "image", "tag", "push", "image"]
    assert all("release" not in command[-1] for command in calls if command[1] in {"tag", "push"})
    docker_hub_digest = "docker.io/kodewaves/api@sha256:" + "c" * 64
    assert build_and_verify._pushed_digest(
        "kodewaves/api:release", json.dumps([docker_hub_digest])
    ) == docker_hub_digest


def test_release_publisher_rejects_tags_without_registry_or_namespace(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "deploy/client"))
    import build_and_verify

    with pytest.raises(ValueError, match="registry or namespace"):
        build_and_verify.push_staging_images(
            "local-api:built", "local-ui:built",
            "local-api:release", "registry.example.com/kodewaves/ui:release",
            release_id="abc123",
        )


def test_release_promotion_preserves_verified_digests(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "deploy/client"))
    import build_and_verify

    api_digest = "registry.example.com/kodewaves/api@sha256:" + "a" * 64
    ui_digest = "registry.example.com/kodewaves/ui@sha256:" + "b" * 64
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[1:4] == ["buildx", "imagetools", "inspect"] and len(command) == 5:
            return SimpleNamespace(returncode=1, stdout="", stderr="manifest unknown")
        if command[1:4] == ["buildx", "imagetools", "inspect"]:
            value = "a" * 64 if "/api:" in command[-1] else "b" * 64
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"digest": "sha256:" + value}),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(build_and_verify.subprocess, "run", run)
    build_and_verify.promote_verified_images(
        ("registry.example.com/kodewaves/api:staging", "registry.example.com/kodewaves/ui:staging"),
        ("registry.example.com/kodewaves/api:release", "registry.example.com/kodewaves/ui:release"),
        (api_digest, ui_digest),
    )

    promotions = [command for command in calls if command[1:4] == ["buildx", "imagetools", "create"]]
    assert len(promotions) == 2
    assert all("--prefer-index=false" in command for command in promotions)
    assert promotions[0][-1] == api_digest
    assert promotions[1][-1] == ui_digest


def test_release_promotion_refuses_to_overwrite_existing_tag(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "deploy/client"))
    import build_and_verify

    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="existing", stderr="")

    monkeypatch.setattr(build_and_verify.subprocess, "run", run)
    with pytest.raises(ValueError, match="Refusing to overwrite existing"):
        build_and_verify.promote_verified_images(
            ("registry.example.com/kodewaves/api:staging", "registry.example.com/kodewaves/ui:staging"),
            ("registry.example.com/kodewaves/api:release", "registry.example.com/kodewaves/ui:release"),
            ("registry.example.com/kodewaves/api@sha256:" + "a" * 64,
             "registry.example.com/kodewaves/ui@sha256:" + "b" * 64),
        )
    assert not any(command[1:4] == ["buildx", "imagetools", "create"] for command in calls)


def test_release_digest_env_is_written_atomically(tmp_path):
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "deploy/client"))
    import build_and_verify

    output = tmp_path / "release.env"
    output.write_text("old release", encoding="utf-8")
    api_digest = "registry.example.com/kodewaves/api@sha256:" + "a" * 64
    ui_digest = "registry.example.com/kodewaves/ui@sha256:" + "b" * 64
    build_and_verify.write_digest_env(output, api_digest, ui_digest)

    assert output.read_text(encoding="utf-8") == (
        f"CLIENT_API_IMAGE={api_digest}\nCLIENT_UI_IMAGE={ui_digest}\n"
    )
    assert not list(tmp_path.glob("*.tmp"))


def test_release_cli_refuses_to_push_unsigned_images(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "deploy/client"))
    import build_and_verify

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_and_verify.py",
            "--api-tag", "registry.example.com/kodewaves/api:release",
            "--ui-tag", "registry.example.com/kodewaves/ui:release",
            "--caddy-image", "registry.example.com/kodewaves/caddy@sha256:" + "d" * 64,
            "--license-public-key-file", str(tmp_path / "license.pub"),
            "--release-public-key-file", str(tmp_path / "release.pub"),
            "--owner-status-url", "https://owner.example.com/check",
            "--push", "--release-env-output", str(tmp_path / "release.env"),
        ],
    )
    with pytest.raises(SystemExit) as error:
        build_and_verify.main()
    assert error.value.code == 2


def test_client_image_verifier_requires_local_administration_without_owner_source():
    root = Path(__file__).resolve().parents[2]
    verifier = (root / "deploy/client/verify_images.py").read_text(encoding="utf-8")
    dockerfile = (root / "api/Dockerfile").read_text(encoding="utf-8")
    assert "api/services/bootstrap_client_admin.py" in verifier
    assert "api/db/client_user_management.py" in verifier
    assert "api/db/client_workspace_management.py" in verifier
    assert "Owner or local secret source shipped" in verifier
    assert "IMAGE_EDITION == 'client'" in verifier
    assert "from api.app import app" in verifier
    assert "Owner-only API routes shipped" in verifier
    assert "'/api/v1/installation/license' in paths" in verifier
    assert "os.getuid() != 0" in verifier
    assert "os.getuid() == 10001" in verifier
    assert "process.getuid() === 0" in verifier
    assert "process.env.KODEWAVES_EDITION !== 'client'" in verifier
    assert "sed -i" in dockerfile and "$KODEWAVES_EDITION" in dockerfile
    ui_dockerfile = (root / "ui/Dockerfile").read_text(encoding="utf-8")
    client_build_pruning = ui_dockerfile.split('RUN if [ "$KODEWAVES_EDITION" = "client" ]; then', 1)[1].split("elif", 1)[0]
    assert "./src/app/impersonate" in client_build_pruning
    assert "privileged" in verifier and "/impersonate/route" in verifier
    ui_runner = ui_dockerfile.split("FROM node:22-alpine AS runner", 1)[1]
    assert "ARG KODEWAVES_EDITION=saas" in ui_runner
    assert "ENV KODEWAVES_EDITION=${KODEWAVES_EDITION}" in ui_runner
    assert "groupadd --gid 10001 kodewaves" in dockerfile
    assert "useradd --uid 10001 --gid 10001" in dockerfile
    assert "mkdir -p /app/kodewaves_pcm_cache" in dockerfile


def test_release_signer_rejects_non_hex_file_hashes(tmp_path):
    root = Path(__file__).resolve().parents[2]
    private = Ed25519PrivateKey.generate()
    private_file = tmp_path / "release-private"
    private_file.write_bytes(private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    ))
    inventory_file = tmp_path / "inventory.json"
    inventory_file.write_text(json.dumps({"api/app.py": "g" * 64}), encoding="utf-8")
    result = subprocess.run([
        sys.executable, str(root / "owner-tools/sign_client_release.py"),
        "--files-json", str(inventory_file), "--private-key", str(private_file),
        "--output", str(tmp_path / "manifest.json"),
    ], check=False, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Protected-file hash inventory is invalid" in result.stderr


def test_release_signer_rejects_noncanonical_private_key_encoding(tmp_path):
    root = Path(__file__).resolve().parents[2]
    private = Ed25519PrivateKey.generate()
    raw_key = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    private_file = tmp_path / "release-private"
    private_file.write_text(
        base64.urlsafe_b64encode(raw_key).rstrip(b"=").decode("ascii") + "===",
        encoding="ascii",
    )
    inventory_file = tmp_path / "inventory.json"
    inventory_file.write_text(json.dumps({"api/app.py": "a" * 64}), encoding="utf-8")
    result = subprocess.run([
        sys.executable, str(root / "owner-tools/sign_client_release.py"),
        "--files-json", str(inventory_file), "--private-key", str(private_file),
        "--output", str(tmp_path / "manifest.json"),
    ], check=False, capture_output=True, text=True)
    assert result.returncode != 0
    assert "canonical URL-safe Base64" in result.stderr


def test_release_builder_rejects_noncanonical_public_key_encoding(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "deploy/client"))
    import build_and_verify

    key = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    encoded = base64.urlsafe_b64encode(key).rstrip(b"=").decode("ascii")
    path = tmp_path / "release-public.key"
    path.write_text(encoded + "===", encoding="ascii")
    with pytest.raises(ValueError, match="Invalid Ed25519 public key"):
        build_and_verify.read_public_key(path)


def test_owner_license_issuer_rejects_overpadded_private_key(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "owner-tools"))
    import issue_client_license

    private = Ed25519PrivateKey.generate()
    raw_key = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    encoded = base64.urlsafe_b64encode(raw_key).decode("ascii")
    with pytest.raises(ValueError, match="invalid URL-safe Base64 length"):
        issue_client_license._decode_key(encoded + "=")


def test_release_signer_accepts_exact_built_image_inventory(tmp_path):
    root = Path(__file__).resolve().parents[2]
    private = Ed25519PrivateKey.generate()
    private_bytes = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    key_file = tmp_path / "release-private"
    key_file.write_bytes(private_bytes)
    inventory = {"api/app.py": "a" * 64, "api/services/owner_public_keys.json": "b" * 64}
    inventory_file = tmp_path / "inventory.json"
    inventory_file.write_text(json.dumps(inventory), encoding="utf-8")
    ui_inventory = {"server.js": "c" * 64, "public/site.css": "d" * 64}
    ui_inventory_file = tmp_path / "ui-inventory.json"
    ui_inventory_file.write_text(json.dumps(ui_inventory), encoding="utf-8")
    manifest_file = tmp_path / "manifest.json"
    public_file = tmp_path / "release-public"

    subprocess.run([
        sys.executable, str(root / "owner-tools/sign_client_release.py"),
        "--files-json", str(inventory_file), "--private-key", str(key_file),
        "--ui-files-json", str(ui_inventory_file),
        "--output", str(manifest_file), "--public-key-output", str(public_file),
    ], check=True, capture_output=True, text=True)

    signed = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert signed["payload"]["files"] == inventory
    assert signed["payload"]["ui_files"] == ui_inventory
    public_text = public_file.read_text().strip()
    public = base64.urlsafe_b64decode(public_text + "=" * (-len(public_text) % 4))
    signature_text = signed["signature"]
    signature = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
    canonical = json.dumps(signed["payload"], sort_keys=True, separators=(",", ":")).encode()
    Ed25519PrivateKey.from_private_bytes(private_bytes).public_key().verify(signature, canonical)
    assert public == private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
