"""Durable best-effort email delivery for owner integrity alerts."""

from datetime import UTC, datetime, timedelta

from loguru import logger

from api.db.client_installations import (
    claim_client_integrity_alert_email,
    get_due_client_integrity_alert_emails,
    mark_client_integrity_alert_email_sent,
    schedule_client_integrity_alert_email_retry,
)
from api.services.client_integrity_notifications import notify_client_integrity_alert
from api.tasks.function_names import FunctionNames

MAX_ATTEMPTS = 6
LEASE_SECONDS = 90
BASE_RETRY_SECONDS = 30
MAX_RETRY_SECONDS = 3600
SWEEP_PAGE_SIZE = 100


def _retry_delay_seconds(attempt: int) -> int:
    """Bound exponential retry delay to one hour."""
    return min(BASE_RETRY_SECONDS * (2 ** max(attempt - 1, 0)), MAX_RETRY_SECONDS)


async def enqueue_client_integrity_alert_email(alert_id: int, attempt: int = 1, defer_by: int = 0) -> None:
    """Best-effort ARQ enqueue; persisted rows are recovered by the sweeper."""
    from api.tasks.arq import enqueue_job

    try:
        await enqueue_job(
            FunctionNames.DELIVER_CLIENT_INTEGRITY_ALERT_EMAIL,
            alert_id,
            _job_id=f"client-integrity-alert-email-{alert_id}-attempt-{attempt}",
            _defer_by=defer_by,
        )
    except Exception as exc:  # noqa: BLE001 - the database row is the durable queue
        logger.warning(
            "Could not enqueue client integrity alert email %s: %s",
            alert_id,
            type(exc).__name__,
        )


async def deliver_client_integrity_alert_email(ctx, alert_id: int) -> None:
    """Send a claimed alert, retry transient/configuration failures, then park it.

    SMTP provides no idempotency key. Delivery is therefore at-least-once: if the
    server accepts a message and this worker dies before marking it sent, lease
    recovery can send one duplicate after 90 seconds.
    """
    del ctx
    alert = await claim_client_integrity_alert_email(alert_id, lease_seconds=LEASE_SECONDS)
    if alert is None:
        return
    attempt = alert["attempt_count"]
    if attempt > MAX_ATTEMPTS:
        await schedule_client_integrity_alert_email_retry(
            alert_id,
            retry_at=datetime.now(UTC),
            error_code="attempt_limit",
            terminal=True,
        )
        return

    delivered = await notify_client_integrity_alert(
        installation_id=alert["installation_id"],
        customer_id=alert["customer_id"],
        finding={
            "reason": alert["reason"],
            "component": alert["component"],
            "expected_sha256": alert["expected_sha256"],
            "observed_sha256": alert["observed_sha256"],
        },
    )
    if delivered:
        await mark_client_integrity_alert_email_sent(alert_id)
        return

    terminal = attempt >= MAX_ATTEMPTS
    retry_at = datetime.now(UTC) + timedelta(seconds=_retry_delay_seconds(attempt))
    await schedule_client_integrity_alert_email_retry(
        alert_id,
        retry_at=retry_at,
        error_code="smtp_delivery_failed",
        terminal=terminal,
    )
    logger.warning(
        f"Client integrity alert email {alert_id} failed on attempt {attempt}"
        f"{'; retry exhausted' if terminal else '; retry scheduled'}"
    )
    if not terminal:
        await enqueue_client_integrity_alert_email(
            alert_id,
            attempt=attempt + 1,
            defer_by=_retry_delay_seconds(attempt),
        )


async def sweep_client_integrity_alert_emails(ctx) -> None:
    """Re-enqueue due work and reclaim expired leases after worker/job loss."""
    del ctx
    after_id = 0
    total = 0
    while True:
        due = await get_due_client_integrity_alert_emails(
            now=datetime.now(UTC), limit=SWEEP_PAGE_SIZE, after_id=after_id,
        )
        if not due:
            break
        for item in due:
            await enqueue_client_integrity_alert_email(
                item["id"], attempt=item["attempt_count"] + 1,
            )
        total += len(due)
        after_id = due[-1]["id"]
        if len(due) < SWEEP_PAGE_SIZE:
            break
    if total:
        logger.info("Client integrity alert email sweep: re-enqueued %s due alerts", total)
