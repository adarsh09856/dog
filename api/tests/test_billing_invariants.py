"""
Unit tests for Kodewaves Billing & Quota Invariants (WP8 / Part 8).

Verifies:
  1. 100% Local sovereign calls charge 0 minutes.
  2. Caller-provided admin/local flags do not bypass platform usage charges.
  3. S2S calls deduct minutes according to the admin s2s_multiplier setting.
  4. Razorpay payment signature verification enforces valid HMAC-SHA256.
  5. Razorpay webhook signature verification validates raw body HMAC.
  6. Deduct minutes records WalletLedgerModel audit entry with balance_after.
"""

import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.routes.payments import (
    verify_razorpay_signature,
    verify_razorpay_webhook_signature,
)
from api.db.kodewaves_client import (
    _materialize_paid_plan_assignment,
    kodewaves_db_client,
)
from api.services.workflow_run_billing import report_workflow_run_platform_usage


@pytest.mark.parametrize("term_days", [30, 365])
def test_wallet_plan_grant_has_the_published_access_duration(term_days):
    from datetime import datetime, timedelta

    result = _materialize_paid_plan_assignment(
        {"plan_code": "pro", "_term_days": term_days}, None
    )
    assert (
        datetime.fromisoformat(result["expires_at"])
        - datetime.fromisoformat(result["updated_at"])
    ) == timedelta(days=term_days)


def test_early_manual_renewal_extends_from_existing_expiry():
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    previous_expiry = now + timedelta(days=10)
    result = _materialize_paid_plan_assignment(
        {"plan_code": "pro", "billing_cycle": "monthly", "_term_days": 30},
        {"plan_code": "pro", "expires_at": previous_expiry.isoformat()},
    )
    actual_expiry = datetime.fromisoformat(result["expires_at"])

    assert timedelta(days=39, hours=23) <= actual_expiry - now <= timedelta(days=40, seconds=1)


def test_switching_plan_starts_new_term_without_carrying_old_plan_time():
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    result = _materialize_paid_plan_assignment(
        {"plan_code": "enterprise", "billing_cycle": "monthly", "_term_days": 30},
        {"plan_code": "starter", "expires_at": (now + timedelta(days=300)).isoformat()},
    )
    expiry = datetime.fromisoformat(result["expires_at"])
    assert timedelta(days=30) <= expiry - now < timedelta(days=30, seconds=2)


@pytest.mark.asyncio
async def test_plan_assignment_and_wallet_credit_commit_together(monkeypatch):
    wallet = SimpleNamespace(credit_balance_minutes=20, updated_at=None)
    assignment = SimpleNamespace(value={"plan_code": "starter"}, category="plan", updated_at=None)

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[None, Result(wallet), Result(None), Result(assignment)]),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    added = []
    session.add = added.append

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def get_session():
        yield session

    monkeypatch.setattr(kodewaves_db_client, "get_session", get_session)
    grant = {"plan_code": "pro", "plan_name": "Pro", "_term_days": 30}

    result = await kodewaves_db_client.add_minutes(
        organization_id=42,
        minutes=100,
        reason="plan_subscription",
        reference_id="payment-1",
        plan_assignment=grant,
    )

    assert result.credit_balance_minutes == 120
    assert assignment.value["plan_code"] == "pro"
    assert assignment.value["plan_name"] == "Pro"
    assert assignment.value["expires_at"]
    assert assignment.category == "plan"
    assert any(getattr(entry, "reference_id", None) == "payment-1" for entry in added)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_payment_does_not_reassign_or_extend_plan(monkeypatch):
    wallet = SimpleNamespace(credit_balance_minutes=120, updated_at=None)
    existing_ledger = SimpleNamespace(id=1)

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[None, Result(wallet), Result(existing_ledger)]),
        add=AsyncMock(), commit=AsyncMock(), refresh=AsyncMock(),
    )

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def get_session():
        yield session

    monkeypatch.setattr(kodewaves_db_client, "get_session", get_session)

    result = await kodewaves_db_client.add_minutes(
        organization_id=42,
        minutes=100,
        reason="plan_subscription",
        reference_id="payment-1",
        plan_assignment={"plan_code": "pro", "_term_days": 30},
    )

    assert result.credit_balance_minutes == 120
    assert session.execute.await_count == 3
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_call_charges_zero_minutes():
    """Invariant: Local sovereign calls must be free (0 minutes deducted)."""
    workflow = SimpleNamespace(organization_id=42)
    workflow_run = SimpleNamespace(
        id=101,
        workflow=workflow,
        mode="local",
        is_completed=True,
        initial_context={"is_local": True},
        gathered_context={"is_local": True},
        usage_info={
            "call_duration_seconds": 180.0,
            "runtime_billing_context": {"version": 1, "sources": ["local"]},
        },
    )

    with patch("api.db.kodewaves_client.kodewaves_db_client.deduct_minutes", new=AsyncMock()) as mock_deduct:
        await report_workflow_run_platform_usage(workflow_run)
        mock_deduct.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_test_prompt_flag_cannot_authorize_a_free_platform_call():
    """Only server-recorded credential attribution can exempt platform charges."""
    workflow = SimpleNamespace(organization_id=42)
    workflow_run = SimpleNamespace(
        id=102,
        workflow=workflow,
        mode="cascade",
        is_completed=True,
        initial_context={"is_admin_test": True},
        gathered_context={"is_admin_test": True},
        usage_info={
            "call_duration_seconds": 120.0,
            "runtime_billing_context": {"version": 1, "sources": ["master_key"]},
        },
    )

    with patch("api.db.kodewaves_client.kodewaves_db_client.deduct_minutes", new=AsyncMock()) as mock_deduct:
        await report_workflow_run_platform_usage(workflow_run)
        mock_deduct.assert_awaited_once_with(
            organization_id=42, minutes=2, reason="call_usage", reference_id="102"
        )


@pytest.mark.asyncio
async def test_s2s_call_applies_admin_multiplier():
    """Invariant: S2S calls deduct at the admin-configured S2S multiplier rate."""
    workflow = SimpleNamespace(organization_id=42)
    workflow_run = SimpleNamespace(
        id=103,
        workflow=workflow,
        mode="s2s",
        is_completed=True,
        initial_context={"is_realtime": True},
        gathered_context={},
        usage_info={
            "call_duration_seconds": 120.0,
            "runtime_billing_context": {
                "version": 1, "sources": ["master_key"], "is_realtime": True,
            },
        },  # 2 minutes
    )

    # Multiplier set to 2.5x in admin pricing settings
    pricing_setting = {"s2s_multiplier": 2.5}

    with (
        patch("api.db.kodewaves_client.kodewaves_db_client.get_setting", new=AsyncMock(return_value=pricing_setting)),
        patch("api.db.kodewaves_client.kodewaves_db_client.deduct_minutes", new=AsyncMock()) as mock_deduct,
    ):
        await report_workflow_run_platform_usage(workflow_run)

        # 2 base minutes * 2.5 = 5 billable minutes
        mock_deduct.assert_awaited_once_with(
            organization_id=42,
            minutes=5,
            reason="s2s_call_usage",
            reference_id="103",
        )


def test_razorpay_signature_verification():
    """Invariant: Paid top-ups require verified HMAC-SHA256 signature."""
    secret = "rzp_test_secret_key_9988"
    order_id = "order_ABCD1234"
    payment_id = "pay_WXYZ5678"

    # Valid signature
    msg = f"{order_id}|{payment_id}".encode("utf-8")
    valid_sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    assert verify_razorpay_signature(order_id, payment_id, valid_sig, secret) is True
    # Tampered signature
    assert verify_razorpay_signature(order_id, payment_id, "forged_signature_123", secret) is False


def test_razorpay_webhook_signature_verification():
    """Invariant: Webhooks require valid HMAC over raw body payload."""
    secret = "rzp_webhook_secret_key_4433"
    raw_body = b'{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_123"}}}}'

    valid_sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    assert verify_razorpay_webhook_signature(raw_body, valid_sig, secret) is True
    assert verify_razorpay_webhook_signature(raw_body, "invalid_sig", secret) is False
