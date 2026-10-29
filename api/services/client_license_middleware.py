"""Enforce signed installation licensing at the API/telephony boundary."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlsplit

from api.constants import KODEWAVES_EDITION
from api.services.installation_license import (
    InstallationFeatureError,
    InstallationLicenseError,
    load_license,
    require_feature,
    validate_installation_license,
)
from api.services.owner_installation_status import require_current_owner_status

ASGIApp = Callable[[dict[str, Any], Callable[..., Awaitable[dict[str, Any]]], Callable[..., Awaitable[None]]], Awaitable[None]]

_FEATURE_PATHS = (
    ("/catalog", "voice"),
    ("/credentials", "voice"),
    ("/folder", "voice"),
    ("/node-types", "voice"),
    ("/organizations/disposition-codes", "voice"),
    ("/organizations/langfuse-credentials", "voice"),
    ("/organizations/overview/stats", "voice"),
    ("/organizations/reports", "voice"),
    ("/organizations/usage", "voice"),
    ("/public/agent", "telephony"),
    ("/public/embed", "widgets"),
    ("/agent-stream", "telephony"),
    ("/appointments", "appointments"),
    ("/billing-sovereign", "billing"),
    ("/campaign", "campaigns"),
    ("/crm", "crm"),
    ("/forms", "forms"),
    ("/knowledge-base", "knowledge_base"),
    ("/mcp", "voice"),
    ("/organizations/campaign-defaults", "campaigns"),
    ("/organizations/call-events", "voice"),
    ("/organizations/concurrent-calls", "voice"),
    ("/organizations/model-configurations", "voice"),
    ("/organizations/preferences", "voice"),
    ("/organizations/reports/workflows", "voice"),
    ("/organizations/telephony-config-warnings", "telephony"),
    ("/organizations/telephony-configs", "telephony"),
    ("/organizations/telephony-providers", "telephony"),
    ("/payments", "billing"),
    ("/prompt-templates", "voice"),
    ("/s3/presigned-upload-url", "campaigns"),
    ("/telephony", "telephony"),
    ("/tools", "voice"),
    ("/turn/credentials", "voice"),
    ("/tts-cache", "voice"),
    ("/user/configurations/voices", "voice"),
    ("/user/configurations", "voice"),
    ("/user/onboarding-state", "voice"),
    ("/user/api-keys", "voice"),
    ("/user/service-keys", "voice"),
    ("/public/download", "voice"),
    ("/widgets", "widgets"),
    ("/workflow-recordings", "voice"),
    ("/workflow", "voice"),
    ("/ws", "voice"),
)


def required_feature_for_path(path: str) -> str | None:
    route_path = path.removeprefix("/api/v1") if path.startswith("/api/v1/") else path
    if re.fullmatch(r"/workflow/\d+/embed-token", route_path):
        return "widgets"
    if route_path == "/ws/public/signaling" or route_path.startswith("/ws/public/signaling/"):
        return "widgets"

    for prefix, feature in _FEATURE_PATHS:
        if route_path == prefix or route_path.startswith(f"{prefix}/"):
            return feature
    return None


def required_feature_for_request(path: str, query_string: bytes = b"") -> str | None:
    """Resolve feature gates for routes whose product depends on the resource key."""
    route_path = path.removeprefix("/api/v1") if path.startswith("/api/v1/") else path
    if route_path in {"/s3/signed-url", "/s3/file-metadata"}:
        query = parse_qs(query_string.decode("latin-1"), keep_blank_values=True)
        keys = query.get("key", [""])
        if len(keys) != 1:
            raise ValueError("Multiple storage keys are not allowed")
        key = keys[0]
        if key.startswith("campaigns/"):
            return "campaigns"
        if key.startswith("knowledge_base/"):
            return "knowledge_base"
        return "voice"
    return required_feature_for_path(path)


def is_owner_control_path(path: str) -> bool:
    """Recognize owner-only route prefixes on both mounted API surfaces."""
    normalized = path.removeprefix("/api/v1") or "/"
    return any(
        normalized == prefix or normalized.startswith(f"{prefix}/")
        for prefix in ("/admin", "/superuser")
    )


def _request_hostname(scope: dict[str, Any]) -> str:
    """Read exactly one syntactically valid HTTP Host for domain binding."""
    hosts = [value for name, value in scope.get("headers", []) if name.lower() == b"host"]
    if len(hosts) != 1:
        raise InstallationLicenseError("Request must contain exactly one valid Host header")
    try:
        authority = hosts[0].decode("ascii")
        parsed = urlsplit(f"//{authority}")
        hostname = parsed.hostname
        # Accessing port validates malformed and out-of-range port values.
        _ = parsed.port
    except (UnicodeDecodeError, ValueError) as exc:
        raise InstallationLicenseError("Request contains an invalid Host header") from exc
    if (
        not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or authority.endswith(":")
        or any(character.isspace() for character in authority)
    ):
        raise InstallationLicenseError("Request contains an invalid Host header")
    return hostname


class ClientLicenseMiddleware:
    """Gate HTTP and websocket data-plane requests in the client edition.

    Health and license-status endpoints remain reachable so operators can
    diagnose an expired or misbound installation. Protected requests bind the
    signed license to their Host header; background checks use the configured
    public origin. Optional IP allowlists use the source address in the owner's
    signed status response, not ``SERVER_IP``.
    """

    _PUBLIC_PATHS: ClassVar[set[str]] = {
        "/",
        "/health",
        "/api/v1/health",
        "/auth/login",
        "/api/v1/auth/login",
        "/auth/me",
        "/api/v1/auth/me",
        "/installation/license",
        "/api/v1/installation/license",
        "/installation/features",
        "/api/v1/installation/features",
        # Identity-signed recovery request must still reach the owner when the
        # current hostname or optional source-IP binding has changed.
    }

    _OWNER_RECOVERY_METHODS: ClassVar[set[tuple[str, str]]] = {
        ("POST", "/installation/binding-requests"),
        ("POST", "/api/v1/installation/binding-requests"),
    }

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if KODEWAVES_EDITION != "client" or scope.get("type") not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self._PUBLIC_PATHS or (scope.get("method", "GET").upper(), path) in self._OWNER_RECOVERY_METHODS or (
            scope.get("method") == "GET"
            and path in {"/installation/branding", "/api/v1/installation/branding"}
        ):
            await self.app(scope, receive, send)
            return

        # Owner control APIs are omitted from client images. Keep a boundary
        # here too so a later accidental router mount cannot expose them.
        if is_owner_control_path(path):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4404, "reason": "Not found"})
                return
            body = json.dumps({"detail": "Not found"}).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 404,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"cache-control", b"no-store"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        try:
            license_data = load_license()
            validate_installation_license(
                license_data,
                request_hostname=_request_hostname(scope),
            )
            await require_current_owner_status(license_data)
            feature = required_feature_for_request(path, scope.get("query_string", b""))
            if feature:
                require_feature(license_data, feature)
        except (InstallationLicenseError, ValueError) as exc:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4403, "reason": str(exc)})
                return
            body = json.dumps({"detail": str(exc)}).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 403 if isinstance(exc, InstallationFeatureError) else 402,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"cache-control", b"no-store"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
