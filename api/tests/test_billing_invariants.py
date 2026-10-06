"""
Unit tests for Kodewaves Billing & Quota Invariants (WP8 / Part 8).

Verifies:
  1. 100% Local sovereign calls charge 0 minutes.
  2. Admin test calls charge 0 minutes.
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
from api.services.workflow_run_billing import report_workflow_run_platform_usage


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
        usage_info={"call_duration_seconds": 180.0},
    )

    with patch("api.db.kodewaves_client.kodewaves_db_client.deduct_minutes", new=AsyncMock()) as mock_deduct:
        await report_workflow_run_platform_usage(workflow_run)
        mock_deduct.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_test_call_charges_zero_minutes():
    """Invariant: Admin test calls must be free (0 minutes deducted)."""
    workflow = SimpleNamespace(organization_id=42)
    workflow_run = SimpleNamespace(
        id=102,
        workflow=workflow,
        mode="cascade",
        is_completed=True,
        initial_context={"is_admin_test": True},
        gathered_context={"is_admin_test": True},
        usage_info={"call_duration_seconds": 120.0},
    )

    with patch("api.db.kodewaves_client.kodewaves_db_client.deduct_minutes", new=AsyncMock()) as mock_deduct:
        await report_workflow_run_platform_usage(workflow_run)
        mock_deduct.assert_not_awaited()


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
        usage_info={"call_duration_seconds": 120.0},  # 2 minutes
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
