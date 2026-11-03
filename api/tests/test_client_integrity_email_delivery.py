from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from api.tasks import client_integrity_email as delivery


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [(1, 30), (2, 60), (3, 120), (7, 1920), (20, 3600)],
)
def test_integrity_email_retry_backoff_is_bounded(attempt, expected):
    assert delivery._retry_delay_seconds(attempt) == expected


@pytest.mark.asyncio
async def test_duplicate_jobs_cannot_send_twice_when_atomic_claim_loses(monkeypatch):
    monkeypatch.setattr(delivery, "claim_client_integrity_alert_email", AsyncMock(return_value=None))
    notify = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery, "notify_client_integrity_alert", notify)

    await delivery.deliver_client_integrity_alert_email({}, 51)
    await delivery.deliver_client_integrity_alert_email({}, 51)

    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_delivery_success_marks_persisted_alert_sent(monkeypatch):
    claim = AsyncMock(return_value={
        "id": 51, "installation_id": "install-51", "customer_id": "customer-51",
        "reason": "modified_file", "component": "api/app.py",
        "expected_sha256": "a" * 64, "observed_sha256": "b" * 64,
        "attempt_count": 1,
    })
    mark_sent = AsyncMock()
    schedule = AsyncMock()
    notify = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery, "claim_client_integrity_alert_email", claim)
    monkeypatch.setattr(delivery, "mark_client_integrity_alert_email_sent", mark_sent)
    monkeypatch.setattr(delivery, "schedule_client_integrity_alert_email_retry", schedule)
    monkeypatch.setattr(delivery, "notify_client_integrity_alert", notify)

    await delivery.deliver_client_integrity_alert_email({}, 51)

    notify.assert_awaited_once()
    mark_sent.assert_awaited_once_with(51)
    schedule.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_delivery_schedules_backoff_retry_and_enqueue(monkeypatch):
    monkeypatch.setattr(delivery, "claim_client_integrity_alert_email", AsyncMock(return_value={
        "id": 51, "installation_id": "install-51", "customer_id": "customer-51",
        "reason": "modified_file", "component": "api/app.py",
        "expected_sha256": None, "observed_sha256": None, "attempt_count": 2,
    }))
    schedule = AsyncMock()
    enqueue = AsyncMock()
    monkeypatch.setattr(delivery, "schedule_client_integrity_alert_email_retry", schedule)
    monkeypatch.setattr(delivery, "enqueue_client_integrity_alert_email", enqueue)
    monkeypatch.setattr(delivery, "notify_client_integrity_alert", AsyncMock(return_value=False))
    before = datetime.now(UTC)

    await delivery.deliver_client_integrity_alert_email({}, 51)

    schedule.assert_awaited_once()
    assert schedule.await_args.args == (51,)
    kwargs = schedule.await_args.kwargs
    assert kwargs["error_code"] == "smtp_delivery_failed"
    assert kwargs["terminal"] is False
    assert before + timedelta(seconds=60) <= kwargs["retry_at"] <= datetime.now(UTC) + timedelta(seconds=60)
    enqueue.assert_awaited_once_with(51, attempt=3, defer_by=60)


@pytest.mark.asyncio
async def test_retry_exhaustion_is_terminal_and_not_reenqueued(monkeypatch):
    monkeypatch.setattr(delivery, "claim_client_integrity_alert_email", AsyncMock(return_value={
        "id": 52, "installation_id": "install-52", "customer_id": "customer-52",
        "reason": "modified_file", "component": "api/app.py",
        "expected_sha256": None, "observed_sha256": None,
        "attempt_count": delivery.MAX_ATTEMPTS,
    }))
    schedule = AsyncMock()
    enqueue = AsyncMock()
    monkeypatch.setattr(delivery, "schedule_client_integrity_alert_email_retry", schedule)
    monkeypatch.setattr(delivery, "enqueue_client_integrity_alert_email", enqueue)
    monkeypatch.setattr(delivery, "notify_client_integrity_alert", AsyncMock(return_value=False))

    await delivery.deliver_client_integrity_alert_email({}, 52)

    assert schedule.await_args.args == (52,)
    assert schedule.await_args.kwargs["terminal"] is True
    assert schedule.await_args.kwargs["error_code"] == "smtp_delivery_failed"
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_attempt_over_max_after_expired_crash_lease_is_parked(monkeypatch):
    monkeypatch.setattr(delivery, "claim_client_integrity_alert_email", AsyncMock(return_value={
        "id": 53, "attempt_count": delivery.MAX_ATTEMPTS + 1,
    }))
    schedule = AsyncMock()
    notify = AsyncMock()
    monkeypatch.setattr(delivery, "schedule_client_integrity_alert_email_retry", schedule)
    monkeypatch.setattr(delivery, "notify_client_integrity_alert", notify)

    await delivery.deliver_client_integrity_alert_email({}, 53)

    assert schedule.await_args.args == (53,)
    assert schedule.await_args.kwargs["terminal"] is True
    assert schedule.await_args.kwargs["error_code"] == "attempt_limit"
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_acknowledged_alert_is_still_retried(monkeypatch):
    # Claim is based on delivery state, independent of acknowledged_at. The
    # acknowledgement only changes owner review state and cannot cancel mail.
    monkeypatch.setattr(delivery, "claim_client_integrity_alert_email", AsyncMock(return_value={
        "id": 54, "installation_id": "install-54", "customer_id": "customer-54",
        "reason": "modified_file", "component": "api/app.py",
        "expected_sha256": None, "observed_sha256": None, "attempt_count": 1,
        "acknowledged_at": datetime.now(UTC),
    }))
    notify = AsyncMock(return_value=True)
    mark_sent = AsyncMock()
    monkeypatch.setattr(delivery, "notify_client_integrity_alert", notify)
    monkeypatch.setattr(delivery, "mark_client_integrity_alert_email_sent", mark_sent)

    await delivery.deliver_client_integrity_alert_email({}, 54)

    notify.assert_awaited_once()
    mark_sent.assert_awaited_once_with(54)
