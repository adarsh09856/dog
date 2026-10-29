"""An operator pause during CSV import must survive worker completion."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.tasks import campaign_tasks


@pytest.mark.asyncio
async def test_sync_completion_does_not_resume_campaign_paused_during_import(monkeypatch):
    campaign = SimpleNamespace(id=17, source_type="csv", source_id="campaigns/2/a.csv")
    paused = SimpleNamespace(state="paused")
    update_if_state = AsyncMock(return_value=False)
    update_campaign = AsyncMock()
    publish_factory = AsyncMock()

    monkeypatch.setattr(
        campaign_tasks.db_client,
        "get_campaign_by_id",
        AsyncMock(side_effect=[campaign, paused]),
    )
    monkeypatch.setattr(
        campaign_tasks.db_client, "update_campaign_if_state", update_if_state
    )
    monkeypatch.setattr(campaign_tasks.db_client, "update_campaign", update_campaign)
    monkeypatch.setattr(
        campaign_tasks, "get_sync_service", lambda _source_type: SimpleNamespace(
            sync_source_data=AsyncMock(return_value=3)
        )
    )
    monkeypatch.setattr(
        campaign_tasks, "get_campaign_event_publisher", publish_factory
    )

    await campaign_tasks.sync_campaign_source({}, 17)

    update_if_state.assert_awaited_once()
    assert update_if_state.await_args.args == (17, "syncing")
    assert update_if_state.await_args.kwargs["state"] == "running"
    update_campaign.assert_awaited_once()
    assert "state" not in update_campaign.await_args.kwargs
    assert update_campaign.await_args.kwargs["source_sync_status"] == "completed"
    publish_factory.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_sync_does_not_complete_campaign_paused_during_import(monkeypatch):
    campaign = SimpleNamespace(id=18, source_type="csv", source_id="campaigns/2/b.csv")
    paused = SimpleNamespace(state="paused")
    update_if_state = AsyncMock(return_value=False)
    update_campaign = AsyncMock()

    monkeypatch.setattr(
        campaign_tasks.db_client,
        "get_campaign_by_id",
        AsyncMock(side_effect=[campaign, paused]),
    )
    monkeypatch.setattr(
        campaign_tasks.db_client, "update_campaign_if_state", update_if_state
    )
    monkeypatch.setattr(campaign_tasks.db_client, "update_campaign", update_campaign)
    monkeypatch.setattr(
        campaign_tasks, "get_sync_service", lambda _source_type: SimpleNamespace(
            sync_source_data=AsyncMock(return_value=0)
        )
    )

    await campaign_tasks.sync_campaign_source({}, 18)

    update_if_state.assert_awaited_once()
    assert update_if_state.await_args.kwargs["state"] == "completed"
    update_campaign.assert_awaited_once()
    assert "state" not in update_campaign.await_args.kwargs
    assert update_campaign.await_args.kwargs["source_sync_status"] == "completed"
