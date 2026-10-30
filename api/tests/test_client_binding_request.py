"""Client binding requests are signed and sent only to the baked owner endpoint."""

import base64
from types import SimpleNamespace

import pytest

from api.routes import installation
from api.services import client_binding_requests as binding_service
from api.services.installation_identity import verify_binding_request


def test_binding_request_url_uses_only_the_baked_check_endpoint(monkeypatch):
    monkeypatch.setattr(
        binding_service,
        "trusted_owner_status_url",
        lambda: "https://owner.example/api/v1/admin/client-installations/check",
    )
    assert binding_service._owner_binding_request_url() == (
        "https://owner.example/api/v1/admin/client-installations/binding-requests"
    )

    monkeypatch.setattr(binding_service, "trusted_owner_status_url", lambda: "https://owner.example/check/other")
    with pytest.raises(binding_service.OwnerTrustError):
        binding_service._owner_binding_request_url()


@pytest.mark.asyncio
async def test_client_admin_sends_signed_canonical_binding_request(monkeypatch, tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public = base64.urlsafe_b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode("ascii")
    key_path = tmp_path / "installation.key"
    key_path.write_bytes(private)
    monkeypatch.setattr(installation, "KODEWAVES_EDITION", "client")
    monkeypatch.setenv("KODEWAVES_LICENSE_TOKEN", "signed-installation-token")
    monkeypatch.setenv("KODEWAVES_INSTALLATION_ID", "install-client-1")
    monkeypatch.setenv("KODEWAVES_INSTALLATION_KEY_FILE", str(key_path))
    monkeypatch.setattr(
        binding_service,
        "load_license",
        lambda token: SimpleNamespace(installation_id="install-client-1"),
    )
    monkeypatch.setattr(
        binding_service,
        "trusted_owner_status_url",
        lambda: "https://owner.example/api/v1/admin/client-installations/check",
    )

    posted = {}

    class Response:
        status_code = 201

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": 8,
                "status": "pending",
                "created_at": "2026-10-29T10:00:00+00:00",
            }

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, json, headers):
            posted.update(url=url, json=json, headers=headers)
            return Response()

    monkeypatch.setattr(binding_service.httpx, "AsyncClient", lambda **_kwargs: Client())
    result = await installation.request_installation_binding_change(
        installation.ClientBindingChangeRequest(
            domains=["Voice.New-Customer.Example", "new-customer.example"],
            ip_ranges=["198.51.100.10", "203.0.113.0/24"],
            reason="Move to a new server",
        ),
        SimpleNamespace(is_superuser=True),
    )
    assert result["request_id"] == 8
    assert posted["url"] == "https://owner.example/api/v1/admin/client-installations/binding-requests"
    assert posted["headers"] == {"Authorization": "Bearer signed-installation-token"}
    proof = posted["json"]
    assert proof["domains"] == ["new-customer.example", "voice.new-customer.example"]
    assert proof["ip_ranges"] == ["198.51.100.10/32", "203.0.113.0/24"]
    verify_binding_request(
        public,
        proof["signature"],
        installation_id="install-client-1",
        license_token="signed-installation-token",
        nonce=proof["nonce"],
        issued_at=proof["issued_at"],
        domains=proof["domains"],
        ip_ranges=proof["ip_ranges"],
        reason=proof["reason"],
    )


@pytest.mark.parametrize("changes", [
    {"domains": ["https://example.com"]},
    {"domains": ["*.example.com"]},
    {"ip_ranges": ["not-an-ip"]},
    {"reason": "   "},
])
def test_binding_request_rejects_invalid_input(changes):
    from pydantic import ValidationError

    fields = dict(domains=["example.com"], ip_ranges=[], reason="Moving servers")
    fields.update(changes)
    with pytest.raises(ValidationError):
        installation.ClientBindingChangeRequest(**fields)


def test_client_binding_import_does_not_require_owner_modules(monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path

    from api.services import deployment_edition

    monkeypatch.setattr(deployment_edition, "IMAGE_EDITION", "client")
    monkeypatch.setitem(sys.modules, "api.db.client_installations", None)
    monkeypatch.setitem(sys.modules, "api.services.owner_license_signer_client", None)
    path = Path(__file__).resolve().parents[1] / "services" / "client_binding_requests.py"
    spec = importlib.util.spec_from_file_location("client_binding_boundary_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.send_binding_request)
