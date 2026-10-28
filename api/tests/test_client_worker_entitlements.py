from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services import client_worker_entitlements as entitlements


@pytest.mark.asyncio
async def test_saas_workers_do_not_require_client_license(monkeypatch):
    monkeypatch.setattr(entitlements, "load_license", lambda: pytest.fail("unexpected license load"))
    monkeypatch.setattr(entitlements, "runtime_edition", lambda: "saas")
    await entitlements.require_client_worker_features("campaigns")


@pytest.mark.asyncio
async def test_client_worker_validates_installation_features_and_owner_status(monkeypatch):
    license_data = SimpleNamespace()
    monkeypatch.setattr(entitlements, "load_license", lambda: license_data)
    monkeypatch.setattr(entitlements, "validate_installation_license", lambda value: assert_same(value, license_data))
    requested = []
    monkeypatch.setattr(entitlements, "require_feature", lambda value, feature: requested.append((value, feature)))
    owner_status = AsyncMock()
    monkeypatch.setattr(entitlements, "require_current_owner_status", owner_status)
    monkeypatch.setattr(entitlements, "runtime_edition", lambda: "client")

    await entitlements.require_client_worker_features("voice", "telephony", "campaigns")

    assert requested == [(license_data, "voice"), (license_data, "telephony"), (license_data, "campaigns")]
    owner_status.assert_awaited_once_with(license_data)


def assert_same(actual, expected):
    assert actual is expected
