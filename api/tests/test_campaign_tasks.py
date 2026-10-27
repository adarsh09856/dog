"""Capacity backpressure completes a batch without failing its campaign."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.tasks import campaign_tasks
from api.tasks.campaign_tasks import process_campaign_batch, sync_campaign_source


@pytest.mark.asyncio
@pytest.mark.parametrize("processed", [0, 5])
async def test_batch_completion_schedules_more_work_without_pool_retry_counters(
    processed,
):
    with (
        patch("api.tasks.campaign_tasks.campaign_call_dispatcher") as dispatcher,
        patch("api.tasks.campaign_tasks.db_client") as db,
        patch(
            "api.tasks.campaign_tasks.get_campaign_event_publisher", AsyncMock()
        ) as get_pub,
    ):
        dispatcher.process_batch = AsyncMock(return_value=processed)
        db.get_campaign_by_id = AsyncMock(return_value=SimpleNamespace(organization_id=206, state="running"))
        with patch("api.tasks.campaign_tasks.enforce_saas_feature", AsyncMock()):
            await process_campaign_batch({}, 48)
        get_pub.return_value.publish_batch_completed.assert_awaited_once_with(
            campaign_id=48, processed_count=processed, failed_count=0, batch_size=20
        )
        db.update_campaign.assert_not_called()


@pytest.mark.asyncio
async def test_shared_setup_failure_is_logged():
    with (
        patch("api.tasks.campaign_tasks.campaign_call_dispatcher") as dispatcher,
        patch("api.tasks.campaign_tasks.db_client") as db,
        patch(
            "api.tasks.campaign_tasks.get_campaign_event_publisher", AsyncMock()
        ) as get_pub,
    ):
        dispatcher.process_batch = AsyncMock(side_effect=ValueError("setup incomplete"))
        db.get_campaign_by_id = AsyncMock(return_value=SimpleNamespace(organization_id=206, state="running"))
        db.update_campaign = AsyncMock()
        db.append_campaign_log = AsyncMock()
        with patch("api.tasks.campaign_tasks.enforce_saas_feature", AsyncMock()):
            with pytest.raises(ValueError):
                await process_campaign_batch({}, 48)
        get_pub.return_value.publish_batch_failed.assert_awaited_once()
        assert db.append_campaign_log.await_args.kwargs["event"] == "batch_failed"


@pytest.mark.asyncio
async def test_client_entitlement_failure_prevents_campaign_dispatch():
    with (
        patch("api.tasks.campaign_tasks.require_client_worker_features", AsyncMock(side_effect=ValueError("campaigns not licensed"))),
        patch("api.tasks.campaign_tasks.campaign_call_dispatcher") as dispatcher,
        patch("api.tasks.campaign_tasks.db_client") as db,
        patch("api.tasks.campaign_tasks.get_campaign_event_publisher", AsyncMock()) as get_pub,
    ):
        dispatcher.process_batch = AsyncMock()
        db.update_campaign = AsyncMock()
        db.append_campaign_log = AsyncMock()
        with pytest.raises(ValueError, match="not licensed"):
            await process_campaign_batch({}, 48)
        dispatcher.process_batch.assert_not_awaited()
        get_pub.return_value.publish_batch_failed.assert_awaited_once()


@pytest.mark.asyncio
async def test_disabled_saas_campaign_feature_blocks_queued_batch(monkeypatch):
    campaign = SimpleNamespace(organization_id=206, state="running")
    db = SimpleNamespace(
        get_campaign_by_id=AsyncMock(return_value=campaign),
        update_campaign=AsyncMock(), append_campaign_log=AsyncMock(),
    )
    feature_check = AsyncMock(side_effect=HTTPException(status_code=403, detail="campaigns disabled"))
    dispatcher = SimpleNamespace(process_batch=AsyncMock())
    publisher = SimpleNamespace(publish_batch_failed=AsyncMock())
    monkeypatch.setattr(campaign_tasks, "require_client_worker_features", AsyncMock())
    monkeypatch.setattr(campaign_tasks, "enforce_saas_feature", feature_check)
    monkeypatch.setattr(campaign_tasks, "db_client", db)
    monkeypatch.setattr(campaign_tasks, "campaign_call_dispatcher", dispatcher)
    monkeypatch.setattr(campaign_tasks, "get_campaign_event_publisher", AsyncMock(return_value=publisher))

    with pytest.raises(HTTPException) as error:
        await process_campaign_batch({}, 48)

    assert error.value.status_code == 403
    feature_check.assert_awaited_once_with(206, "campaigns")
    dispatcher.process_batch.assert_not_awaited()
    publisher.publish_batch_failed.assert_awaited_once()


@pytest.mark.asyncio
async def test_paused_campaign_does_not_fail_when_its_feature_is_disabled(monkeypatch):
    db = SimpleNamespace(
        get_campaign_by_id=AsyncMock(return_value=SimpleNamespace(organization_id=206, state="paused")),
        update_campaign=AsyncMock(), append_campaign_log=AsyncMock(),
    )
    feature_check = AsyncMock(side_effect=HTTPException(status_code=403, detail="campaigns disabled"))
    dispatcher = SimpleNamespace(process_batch=AsyncMock(return_value=0))
    publisher = SimpleNamespace(publish_batch_completed=AsyncMock())
    monkeypatch.setattr(campaign_tasks, "require_client_worker_features", AsyncMock())
    monkeypatch.setattr(campaign_tasks, "enforce_saas_feature", feature_check)
    monkeypatch.setattr(campaign_tasks, "db_client", db)
    monkeypatch.setattr(campaign_tasks, "campaign_call_dispatcher", dispatcher)
    monkeypatch.setattr(campaign_tasks, "get_campaign_event_publisher", AsyncMock(return_value=publisher))

    await process_campaign_batch({}, 48)

    feature_check.assert_not_awaited()
    db.update_campaign.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_saas_campaign_feature_blocks_queued_source_sync(monkeypatch):
    events = []
    campaign = SimpleNamespace(id=48, organization_id=206, source_type="crm", source_id="source-1")
    db = SimpleNamespace(
        get_campaign_by_id=AsyncMock(side_effect=lambda _id: events.append("campaign") or campaign),
        update_campaign=AsyncMock(),
        append_campaign_log=AsyncMock(),
    )
    async def sync_source_data(*_args):
        events.append("source_sync")
        return 0

    sync = SimpleNamespace(sync_source_data=AsyncMock(side_effect=sync_source_data))
    feature_check = AsyncMock(
        side_effect=lambda *_: events.append("feature_check")
        or (_ for _ in ()).throw(HTTPException(status_code=403, detail="campaigns disabled"))
    )
    monkeypatch.setattr(campaign_tasks, "require_client_worker_features", AsyncMock())
    monkeypatch.setattr(campaign_tasks, "enforce_saas_feature", feature_check, raising=False)
    monkeypatch.setattr(campaign_tasks, "db_client", db)
    monkeypatch.setattr(campaign_tasks, "get_sync_service", lambda _source_type: sync)

    with pytest.raises(HTTPException, match="campaigns disabled"):
        await sync_campaign_source({}, campaign_id=48)

    feature_check.assert_awaited_once_with(206, "campaigns")
    sync.sync_source_data.assert_not_awaited()
    assert events == ["campaign", "feature_check"]
