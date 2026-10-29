from datetime import UTC, datetime
from typing import Dict

from loguru import logger

from api.db import db_client
from api.services.campaign.campaign_call_dispatcher import campaign_call_dispatcher
from api.services.campaign.campaign_event_publisher import (
    get_campaign_event_publisher,
)
from api.services.campaign.source_sync_factory import get_sync_service


async def _finish_source_sync(
    campaign_id: int,
    state: str,
    *,
    values: dict,
    paused_values: dict,
) -> bool:
    """Finalize an import without overwriting a concurrent pause/cancel."""
    if await db_client.update_campaign_if_state(
        campaign_id, "syncing", state=state, **values
    ):
        return True

    campaign = await db_client.get_campaign_by_id(campaign_id)
    if campaign is not None and campaign.state == "paused":
        # Preserve the operator's pause while recording that import finished.
        await db_client.update_campaign(campaign_id, **paused_values)
    return False


async def sync_campaign_source(ctx: Dict, campaign_id: int) -> None:
    """
    Phase 1: Syncs data from configured source to queued_runs table
    - Campaign state should already be 'syncing'
    - Determines source type from campaign configuration
    - Fetches data via the appropriate sync service
    - Creates queued_run entries with unique source_uuid
    - Updates campaign total_rows
    - Transitions campaign state to 'running' on success
    - Enqueues process_campaign_batch tasks
    """
    logger.info(f"Starting source sync for campaign {campaign_id}")

    try:
        # Get campaign
        campaign = await db_client.get_campaign_by_id(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        # Get appropriate sync service
        sync_service = get_sync_service(campaign.source_type)

        # Sync source data
        rows_synced = await sync_service.sync_source_data(campaign_id)

        if rows_synced == 0:
            # No data to process
            await _finish_source_sync(
                campaign_id,
                state="completed",
                values={
                    "completed_at": datetime.now(UTC),
                    "source_sync_status": "completed",
                    "source_last_synced_at": datetime.now(UTC),
                },
                paused_values={
                    "source_sync_status": "completed",
                    "source_last_synced_at": datetime.now(UTC),
                },
            )
            logger.info(f"Campaign {campaign_id} completed with no data to process")
            return

        # Update campaign state to running
        transitioned = await _finish_source_sync(
            campaign_id,
            state="running",
            values={
                "source_sync_status": "completed",
                "source_last_synced_at": datetime.now(UTC),
            },
            paused_values={
                "source_sync_status": "completed",
                "source_last_synced_at": datetime.now(UTC),
            },
        )
        if not transitioned:
            logger.info(
                f"Campaign {campaign_id} left syncing during import; "
                "preserving its current state and not dispatching contacts"
            )
            return

        # Publish sync completed event - orchestrator will schedule first batch
        publisher = await get_campaign_event_publisher()
        await publisher.publish_sync_completed(
            campaign_id=campaign_id,
            total_rows=rows_synced,
            source_type=campaign.source_type,
            source_id=campaign.source_id,
        )

        logger.info(
            f"Campaign {campaign_id} source sync completed, {rows_synced} rows synced"
        )

    except Exception as e:
        logger.error(f"Error syncing campaign {campaign_id} source: {e}")

        # Do not replace a concurrent pause/cancel with a stale failure state.
        failed_transition = await db_client.update_campaign_if_state(
            campaign_id,
            "syncing",
            state="failed",
            source_sync_status="failed",
            source_sync_error=str(e),
        )
        if not failed_transition:
            campaign = await db_client.get_campaign_by_id(campaign_id)
            if campaign is not None and campaign.state == "paused":
                await db_client.update_campaign(
                    campaign_id=campaign_id,
                    source_sync_status="failed",
                    source_sync_error=str(e),
                )
        await db_client.append_campaign_log(
            campaign_id=campaign_id,
            level="error",
            event="source_sync_failed",
            message=f"Source sync failed: {e}",
            details={"error": str(e)},
        )
        raise


async def process_campaign_batch(
    ctx: Dict, campaign_id: int, batch_size: int = 20
) -> None:
    """
    Phase 2: Processes a batch of queued runs
    - Fetches next batch of 'queued' runs (including due retries)
    - Creates workflow runs with context variables
    - Initiates Twilio calls with rate limiting
    - Updates queued_run state to 'processed'
    - Updates campaign.processed_rows counter
    - Publishes batch_completed event for orchestrator

    # TODO: May be not fail the campaign immediately on a single batch failure
    # and propagate the error to campaign orchestrator which can fail the campaign
    # on some consecutive batch failures.
    """
    logger.info(f"Processing batch for campaign {campaign_id}, batch_size={batch_size}")

    failed_count = 0
    try:
        # Process the batch
        processed_count = await campaign_call_dispatcher.process_batch(
            campaign_id=campaign_id, batch_size=batch_size
        )

        # Publish batch completed event - orchestrator will handle next batch scheduling
        publisher = await get_campaign_event_publisher()
        await publisher.publish_batch_completed(
            campaign_id=campaign_id,
            processed_count=processed_count,
            failed_count=failed_count,
            batch_size=batch_size,
        )

        logger.info(
            f"Campaign {campaign_id} batch completed: processed={processed_count}, "
            f"failed={failed_count}"
        )

    except Exception as e:
        logger.error(f"Error processing batch for campaign {campaign_id}: {e}")

        # Publish batch failed event
        publisher = await get_campaign_event_publisher()
        await publisher.publish_batch_failed(
            campaign_id=campaign_id,
            error=str(e),
            processed_count=0,
        )

        # Update campaign state to failed
        await db_client.update_campaign(campaign_id=campaign_id, state="failed")
        await db_client.append_campaign_log(
            campaign_id=campaign_id,
            level="error",
            event="batch_failed",
            message=f"Batch processing failed: {e}",
            details={"error": str(e)},
        )
        raise
