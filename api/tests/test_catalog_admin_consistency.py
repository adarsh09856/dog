from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.db.kodewaves_models import AIModelCatalogModel
from api.routes.admin.models import ModelCatalogItem, _catalog_values
from api.services.catalog.catalog_service import CatalogService
from api.services.worker_sync.protocol import WorkerSyncEventType


def test_admin_can_explicitly_set_free_price():
    values = _catalog_values(ModelCatalogItem(
        model_id="example", display_name="Example", provider=" OPENAI ", category="tts",
        base_cost_cents_per_unit=5, retail_price_cents_per_unit=10,
        cost_per_minute=0, rate_per_minute=0,
    ))
    assert values["base_cost_cents_per_unit"] == 0
    assert values["retail_price_cents_per_unit"] == 0
    assert values["provider"] == "openai"


@pytest.mark.asyncio
async def test_catalog_change_invalidates_and_broadcasts(monkeypatch):
    service = CatalogService()
    service._cache["org"] = (0, {"old": True})
    manager = SimpleNamespace(broadcast=AsyncMock())
    monkeypatch.setattr("api.services.worker_sync.manager.get_worker_sync_manager", lambda: manager)
    await service.notify_changed()
    assert service._cache == {}
    manager.broadcast.assert_awaited_once_with(WorkerSyncEventType.MODEL_CATALOG, "update")


@pytest.mark.asyncio
@pytest.mark.parametrize("category,layer", [("tts", "tts"), ("stt", "stt"), ("sts", "s2s")])
async def test_admin_save_keeps_runtime_layer_and_enabled_state_consistent(monkeypatch, category, layer):
    from api.db.kodewaves_client import kodewaves_db_client
    record = AIModelCatalogModel(model_identifier="example", supports_tools=True)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, statement):
            return SimpleNamespace(scalar_one_or_none=lambda: record)

        async def commit(self):
            pass

    monkeypatch.setattr(kodewaves_db_client, "get_session", lambda: Session())
    values = _catalog_values(ModelCatalogItem(
        model_id="example", display_name="Example", provider="openai", category=category,
        is_active=False,
    ))
    result = await kodewaves_db_client.configure_admin_model(values)
    assert result.layer == layer
    assert result.enabled is False and result.is_active is False
    assert result.supports_tools is True
