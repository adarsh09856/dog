"""New credit bundle activation requires an explicit price decision."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.db import credit_package_catalog
from api.routes.admin import credit_packages


@pytest.mark.asyncio
async def test_new_active_credit_bundle_without_explicit_price_is_rejected(monkeypatch):
    create_package = AsyncMock(side_effect=AssertionError("Invalid bundle reached the catalog"))
    monkeypatch.setattr(credit_package_catalog, "create_package", create_package)
    payload = credit_packages.CreditPackageItem(
        name="Unpriced", minutes=100, is_active=True,
    )

    with pytest.raises(HTTPException) as rejected:
        await credit_packages.create_credit_package(payload, _user=SimpleNamespace(id=1))

    assert rejected.value.status_code == 422
    create_package.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_explicitly_free_credit_bundle_is_accepted(monkeypatch):
    create_package = AsyncMock(return_value=SimpleNamespace(id="free-bundle"))
    monkeypatch.setattr(credit_package_catalog, "create_package", create_package)
    payload = credit_packages.CreditPackageItem(
        name="Free", minutes=100, price_cents=0, is_active=True,
    )

    await credit_packages.create_credit_package(payload, _user=SimpleNamespace(id=1))

    assert create_package.await_args.args[0]["price_cents"] == 0


@pytest.mark.asyncio
async def test_existing_credit_bundle_edit_can_retain_zero_price(monkeypatch):
    update_package = AsyncMock(return_value=SimpleNamespace(id="existing-id", name="Existing Free"))
    monkeypatch.setattr(credit_package_catalog, "update_package", update_package)
    payload = credit_packages.CreditPackageItem(
        name="Existing Free", minutes=100, price_cents=0, is_active=True,
    )

    await credit_packages.update_credit_package("existing-id", payload, _user=SimpleNamespace(id=1))

    update_package.assert_awaited_once()
