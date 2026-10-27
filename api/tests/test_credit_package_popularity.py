"""Owner-selected popularity must survive writes and reach both store APIs."""

import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.db import credit_package_catalog
from api.routes import billing_sovereign
from api.routes.admin import credit_packages


@pytest.mark.asyncio
@pytest.mark.parametrize("bonus,popular", [(50, False), (0, True)])
async def test_owner_setting_survives_create_update_and_both_store_responses(monkeypatch, bonus, popular):
    records = []

    def add(record):
        record.id = uuid.uuid4()
        records.append(record)

    session = SimpleNamespace(
        add=add, commit=AsyncMock(), refresh=AsyncMock(),
        execute=AsyncMock(side_effect=lambda *_: SimpleNamespace(
            scalar_one_or_none=lambda: records[0],
            scalars=lambda: SimpleNamespace(all=lambda: records),
        )),
    )

    @asynccontextmanager
    async def get_session():
        yield session

    monkeypatch.setattr(credit_package_catalog.kodewaves_db_client, "get_session", get_session)
    pkg = credit_packages.CreditPackageItem(
        name="Configured bundle", minutes=100, bonus_minutes=bonus,
        price_cents=1200, is_popular=popular,
    )
    created = await credit_packages.create_credit_package(pkg, _user=None)
    assert records[0].is_popular is popular
    await credit_packages.update_credit_package(created["id"], pkg, _user=None)
    assert (await credit_packages.list_credit_packages(_user=None))[0].is_popular is popular
    assert session.refresh.await_count == 2

    monkeypatch.setattr(billing_sovereign, "list_active_credit_packages", AsyncMock(return_value=records))
    assert (await billing_sovereign.list_public_packages())[0].is_popular is popular
    assert (await billing_sovereign.list_available_packages(_user=None))[0].is_popular is popular


def test_published_api_schema_contains_popularity_field():
    root = Path(__file__).resolve().parents[2]
    published = json.loads((root / "docs/api-reference/openapi.json").read_text(encoding="utf-8"))
    documented = published["components"]["schemas"]["CreditPackagePublicItem"]["properties"]["is_popular"]
    actual = billing_sovereign.CreditPackagePublicItem.model_json_schema()["properties"]["is_popular"]
    assert documented == actual
