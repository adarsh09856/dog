"""Regression coverage for reverse-proxy trust on supported deployments."""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


ROOT = Path(__file__).resolve().parents[2]


def test_compose_stacks_do_not_use_wildcard_forwarded_header_trust():
    bundled = yaml.safe_load((ROOT / "docker-compose.yaml").read_text(encoding="utf-8"))
    api_env = bundled["services"]["api"]["environment"]
    nginx_network = bundled["services"]["nginx"]["networks"]["app-network"]
    assert nginx_network["ipv4_address"] == "${NGINX_IPV4:-172.30.0.2}"
    assert api_env["FORWARDED_ALLOW_IPS"] == "${NGINX_IPV4:-172.30.0.2}"
    assert bundled["networks"]["app-network"]["ipam"]["config"][0]["subnet"] == (
        "${KODEWAVES_NETWORK_SUBNET:-172.30.0.0/24}"
    )

    aapanel = yaml.safe_load((ROOT / "docker-compose.aapanel.yaml").read_text(encoding="utf-8"))
    aapanel_env = aapanel["services"]["api"]["environment"]
    assert aapanel_env["FORWARDED_ALLOW_IPS"] == "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    updater = (ROOT / "deploy.sh").read_text(encoding="utf-8")
    assert "docker inspect kodewaves_postgres --format" in installer
    assert "FORWARDED_ALLOW_IPS=$proxy_peer" in installer
    assert "docker inspect kodewaves_postgres --format" in updater
    assert "FORWARDED_ALLOW_IPS=$PROXY_PEER" in updater

    hostinger = yaml.safe_load(
        (ROOT / "deploy/hostinger/docker-compose.yaml").read_text(encoding="utf-8")
    )
    hostinger_value = hostinger["services"]["api"]["environment"]["FORWARDED_ALLOW_IPS"]
    assert hostinger_value == "${FORWARDED_ALLOW_IPS:?Set the trusted Traefik peer IP or CIDR}"


def _proxy_result(trusted_hosts: str, forwarded_for: str) -> str:
    observed: list[str] = []

    async def app(scope, receive, send):
        observed.append(scope["client"][0])

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [
            (b"x-forwarded-for", forwarded_for.encode("ascii")),
            (b"x-forwarded-proto", b"https"),
        ],
        "client": ("172.30.0.2", 54321),
        "server": ("127.0.0.1", 8000),
    }
    asyncio.run(ProxyHeadersMiddleware(app, trusted_hosts=trusted_hosts)(scope, receive, send))
    return observed[0]


def test_uvicorn_trusted_ingress_uses_proxy_appended_client_ip_not_spoofed_prefix():
    # The caller supplies a fake first XFF value; nginx appends the actual peer.
    xff = "198.51.100.77, 203.0.113.44"
    assert _proxy_result("172.30.0.2", xff) == "203.0.113.44"
    # This assertion captures why wildcard proxy trust must remain forbidden.
    assert _proxy_result("*", xff) == "198.51.100.77"
