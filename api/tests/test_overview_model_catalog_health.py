from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.routes import organization
from api.routes.organization import _catalog_models_for_layer
from api.services.call_concurrency import call_concurrency


def _stub_overview_dependencies(monkeypatch):
    monkeypatch.setattr(
        organization.db_client, "get_all_workflows", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        organization.db_client,
        "get_usage_history",
        AsyncMock(return_value=([], 0, None, None)),
    )
    monkeypatch.setattr(
        call_concurrency, "get_org_active_calls", AsyncMock(return_value=0)
    )
    from api.services.catalog.catalog_service import catalog_service

    monkeypatch.setattr(catalog_service, "get_available_catalog", AsyncMock(return_value={}))


def test_catalog_model_health_includes_cloud_and_self_hosted_models():
    catalog = {
        "cloud_llm_models": [{"id": "cloud-llm"}],
        "local_llm_models": [{"id": "local-llm"}],
        "cloud_stt_models": [{"id": "cloud-stt"}],
        "local_stt_models": [{"id": "local-stt"}],
        "cloud_tts_models": [{"id": "cloud-tts"}],
        "local_tts_models": [{"id": "local-tts"}],
        "cloud_s2s_models": [{"id": "cloud-realtime"}],
        "local_s2s_models": [{"id": "local-realtime"}],
    }

    assert [model["id"] for model in _catalog_models_for_layer(catalog, "llm")] == [
        "cloud-llm",
        "local-llm",
    ]
    assert [model["id"] for model in _catalog_models_for_layer(catalog, "stt")] == [
        "cloud-stt",
        "local-stt",
    ]
    assert [model["id"] for model in _catalog_models_for_layer(catalog, "tts")] == [
        "cloud-tts",
        "local-tts",
    ]
    assert [model["id"] for model in _catalog_models_for_layer(catalog, "realtime")] == [
        "cloud-realtime",
        "local-realtime",
    ]


def test_catalog_model_health_keeps_legacy_layer_keys():
    catalog = {"llm": [{"id": "legacy-llm"}], "stt": [], "tts": []}

    assert [model["id"] for model in _catalog_models_for_layer(catalog, "llm")] == [
        "legacy-llm"
    ]
    assert _catalog_models_for_layer(catalog, "stt") == []


@pytest.mark.asyncio
async def test_client_overview_does_not_read_wallet_without_billing_license(monkeypatch):
    monkeypatch.setattr(organization, "KODEWAVES_EDITION", "client")
    monkeypatch.setattr(
        organization, "load_license", lambda: SimpleNamespace(features={"voice"})
    )
    wallet_read = AsyncMock(side_effect=AssertionError("unlicensed wallet read"))
    monkeypatch.setattr(organization.kodewaves_db_client, "get_or_create_wallet", wallet_read)
    _stub_overview_dependencies(monkeypatch)

    result = await organization.get_organization_overview_stats(
        SimpleNamespace(selected_organization_id=42)
    )

    assert result["wallet"] is None
    wallet_read.assert_not_awaited()


@pytest.mark.asyncio
async def test_client_overview_returns_wallet_only_with_billing_license(monkeypatch):
    monkeypatch.setattr(organization, "KODEWAVES_EDITION", "client")
    monkeypatch.setattr(
        organization,
        "load_license",
        lambda: SimpleNamespace(features={"voice", "billing"}),
    )
    wallet_read = AsyncMock(
        return_value=SimpleNamespace(credit_balance_minutes=12.5, bonus_minutes=2.0)
    )
    monkeypatch.setattr(organization.kodewaves_db_client, "get_or_create_wallet", wallet_read)
    _stub_overview_dependencies(monkeypatch)

    result = await organization.get_organization_overview_stats(
        SimpleNamespace(selected_organization_id=42)
    )

    assert result["wallet"] == {
        "credit_balance_minutes": 12.5,
        "bonus_minutes": 2.0,
        "total_minutes": 14.5,
    }
    wallet_read.assert_awaited_once_with(42)
