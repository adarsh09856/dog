"""Test doubles for the isolated owner license signing service."""

from unittest.mock import AsyncMock

from api.services.installation_license import InstallationLicenseError, issue_license_token, load_license


def mock_owner_signer(monkeypatch, route_module, *signer_pairs):
    """Patch public-key lookup and status signing with test-only private keys."""
    assert signer_pairs
    if hasattr(route_module, "owner_license_public_keys"):
        monkeypatch.setattr(
            route_module,
            "owner_license_public_keys",
            AsyncMock(return_value=tuple(public for _private, public in signer_pairs)),
        )

    async def sign_for_license(claims, license_token):
        for private, public in signer_pairs:
            try:
                load_license(license_token, public)
            except InstallationLicenseError:
                continue
            return issue_license_token(claims, private)
        raise AssertionError("No test signer matches the supplied owner license")

    if hasattr(route_module, "sign_installation_status"):
        monkeypatch.setattr(
            route_module,
            "sign_installation_status",
            AsyncMock(side_effect=sign_for_license),
        )

    async def issue_license(claims):
        private, public = signer_pairs[0]
        return issue_license_token(claims, private), public

    if hasattr(route_module, "sign_client_license"):
        monkeypatch.setattr(route_module, "sign_client_license", AsyncMock(side_effect=issue_license))
