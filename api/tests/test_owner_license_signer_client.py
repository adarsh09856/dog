"""The private signer must not use proxy settings inherited from the host."""

import asyncio

import httpx
import pytest

from api.services import owner_license_signer_client as signer


def test_signer_requests_ignore_proxy_environment(monkeypatch):
    monkeypatch.setenv("KODEWAVES_OWNER_LICENSE_SIGNER_URL", "http://owner-license-signer:8765")
    monkeypatch.setenv("KODEWAVES_OWNER_LICENSE_SIGNER_TOKEN", "t" * 48)
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:8080")
    options = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"public_keys": ["public"], "token": "signed", "public_key": "public"}

    class Client:
        def __init__(self, **kwargs):
            options.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def get(self, *_args, **_kwargs):
            return Response()

        async def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(signer.httpx, "AsyncClient", Client)
    assert asyncio.run(signer.owner_license_public_keys()) == ("public",)
    assert asyncio.run(signer.sign_client_license({})) == ("signed", "public")
    assert len(options) == 2
    assert all(option["trust_env"] is False for option in options)


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (422, signer.OwnerLicenseSignerPolicyError),
        (503, signer.OwnerLicenseSignerError),
    ],
)
def test_signer_distinguishes_policy_rejection_from_unavailability(
    monkeypatch, status_code, expected_error,
):
    monkeypatch.setenv("KODEWAVES_OWNER_LICENSE_SIGNER_URL", "http://owner-license-signer:8765")
    monkeypatch.setenv("KODEWAVES_OWNER_LICENSE_SIGNER_TOKEN", "t" * 48)

    class Response:
        def __init__(self):
            self.status_code = status_code

        def raise_for_status(self):
            request = httpx.Request("POST", "http://owner-license-signer:8765/v1/sign-license")
            raise httpx.HTTPStatusError("rejected", request=request, response=self)

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(signer.httpx, "AsyncClient", Client)
    with pytest.raises(expected_error) as error:
        asyncio.run(signer.sign_client_license({}))
    if status_code == 503:
        assert type(error.value) is signer.OwnerLicenseSignerError
