from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import httpx
from contextlib import asynccontextmanager

from api.routes import billing_sovereign
from api.routes.billing_sovereign import _legacy_plan_prices, _requires_paid_checkout
from api.routes.admin.plans import PlanItem, _configured_monthly_price_cents
from api.routes.admin.credit_packages import CreditPackageItem, _configured_package_price_cents
from api.routes.payments import (
    _grant_paid_order,
    _minor_units_to_gateway_units,
    _order_organization_id,
    _plan_price_for_checkout,
    _fetch_paid_order,
    _validate_order_metadata,
    VerifyPaymentRequest,
    verify_razorpay_signature,
    verify_razorpay_webhook_signature,
)
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes import payments
from api.db import public_pricing


def test_public_plan_prices_expose_inr_without_estimating_usd():
    assert _legacy_plan_prices(249900, "INR") == (2499, None)


def test_public_plan_prices_expose_usd_without_estimating_inr():
    assert _legacy_plan_prices(2999, "USD") == (None, 29.99)


def test_public_plan_prices_hide_legacy_amounts_for_unknown_currency():
    assert _legacy_plan_prices(149900, "unknown") == (None, None)


@pytest.mark.asyncio
async def test_public_plan_query_filters_private_and_inactive_catalog_entries(monkeypatch):
    plan = SimpleNamespace(is_active=True, is_public=True)
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [plan]))
    session = SimpleNamespace(execute=AsyncMock(return_value=result))

    @asynccontextmanager
    async def get_session():
        yield session

    monkeypatch.setattr(public_pricing.kodewaves_db_client, "get_session", get_session)
    assert await public_pricing.list_active_plans() == [plan]
    query = str(session.execute.await_args.args[0])
    assert "saas_plans.is_active IS true" in query
    assert "saas_plans.is_public IS true" in query


def test_annual_only_paid_plan_requires_checkout():
    plan = SimpleNamespace(monthly_price_cents=0, annual_price_cents=12000)
    assert _requires_paid_checkout("annual", plan)
    assert _requires_paid_checkout("starter", plan)
    assert not _requires_paid_checkout(
        "starter", SimpleNamespace(monthly_price_cents=0, annual_price_cents=0)
    )


def test_admin_plan_uses_explicit_minor_units_even_when_price_is_zero():
    plan = PlanItem(
        name="Free", code="free", currency="INR", monthly_price_cents=0,
        monthly_price_inr=4999,
    )
    assert _configured_monthly_price_cents(plan) == 0


def test_admin_plan_legacy_fallback_uses_only_the_selected_currency():
    inr = PlanItem(name="INR", code="inr", currency="INR", monthly_price_inr=4999)
    usd = PlanItem(name="USD", code="usd", currency="USD", monthly_price_usd=59)
    wrong_currency = PlanItem(name="USD", code="wrong", currency="USD", monthly_price_inr=4999)
    assert _configured_monthly_price_cents(inr) == 499900
    assert _configured_monthly_price_cents(usd) == 5900
    assert _configured_monthly_price_cents(wrong_currency) == 0


def test_credit_package_legacy_fallback_uses_only_the_selected_currency():
    inr = CreditPackageItem(name="INR", minutes=100, currency="INR", price_inr=499)
    usd = CreditPackageItem(name="USD", minutes=100, currency="USD", price_usd=5)
    wrong_currency = CreditPackageItem(name="USD", minutes=100, currency="USD", price_inr=499)
    assert _configured_package_price_cents(inr) == 49900
    assert _configured_package_price_cents(usd) == 500
    assert _configured_package_price_cents(wrong_currency) == 0


def test_explicit_zero_credit_package_price_is_not_replaced_by_legacy_amount():
    package = CreditPackageItem(
        name="Free", minutes=100, currency="INR", price_cents=0, price_inr=499,
    )
    assert _configured_package_price_cents(package) == 0


def test_payment_amount_minor_units_are_never_scaled_twice():
    assert _minor_units_to_gateway_units(2999) == 2999
    assert _minor_units_to_gateway_units(0) == 0


def test_annual_only_plan_cannot_create_a_zero_amount_monthly_checkout():
    annual_only = SimpleNamespace(monthly_price_cents=0, annual_price_cents=12000)
    assert _plan_price_for_checkout(annual_only, "annual") == 12000
    with pytest.raises(HTTPException):
        _plan_price_for_checkout(annual_only, "monthly")


def test_payment_signatures_fail_closed_when_secrets_or_signatures_are_missing():
    assert not verify_razorpay_signature("order", "payment", "", "")
    assert not verify_razorpay_webhook_signature(b"{}", "", "")


def test_paid_order_metadata_is_bound_to_organization_and_one_catalog_item():
    package_id, plan_code, cycle = _validate_order_metadata(
        {"organization_id": "42", "package_id": "pkg-1", "plan_code": "", "billing_cycle": "monthly"},
        42,
    )
    assert (package_id, plan_code, cycle) == ("pkg-1", "", "monthly")
    assert _order_organization_id({"organization_id": "42"}) == 42
    with pytest.raises(HTTPException):
        _validate_order_metadata(
            {"organization_id": "41", "package_id": "pkg-1", "plan_code": ""}, 42,
        )
    with pytest.raises(HTTPException):
        _validate_order_metadata(
            {"organization_id": "42", "package_id": "pkg-1", "plan_code": "starter"}, 42,
        )
    with pytest.raises(HTTPException):
        _validate_order_metadata(
            {"organization_id": "42", "package_id": "pkg-1", "plan_code": "", "billing_cycle": "daily"},
            42,
        )
    with pytest.raises(HTTPException):
        _order_organization_id({"organization_id": "not-an-org"})


@pytest.mark.asyncio
async def test_paid_starter_plan_cannot_be_activated_through_free_endpoint(monkeypatch):
    plan = SimpleNamespace(
        code="starter", name="Starter", is_active=True, is_public=True,
        monthly_price_cents=1000, annual_price_cents=0,
    )

    class Session:
        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: plan)

    @asynccontextmanager
    async def get_session():
        yield Session()

    monkeypatch.setattr(billing_sovereign.kodewaves_db_client, "get_session", get_session)
    credit = AsyncMock()
    monkeypatch.setattr(billing_sovereign.kodewaves_db_client, "add_minutes", credit)
    with pytest.raises(HTTPException) as error:
        await billing_sovereign.subscribe_to_plan(
            billing_sovereign.SubscribePlanRequest(plan_code="starter"),
            SimpleNamespace(selected_organization_id=42),
        )
    assert error.value.status_code == 402
    credit.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_paid_catalog_item_does_not_fall_back_to_trial_credit(monkeypatch):
    class Session:
        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: None)

    @asynccontextmanager
    async def get_session():
        yield Session()

    monkeypatch.setattr(billing_sovereign.kodewaves_db_client, "get_session", get_session)
    credit = AsyncMock()
    monkeypatch.setattr(billing_sovereign.kodewaves_db_client, "add_minutes", credit)
    with pytest.raises(HTTPException) as error:
        await billing_sovereign.subscribe_to_plan(
            billing_sovereign.SubscribePlanRequest(plan_code="unconfigured"),
            SimpleNamespace(selected_organization_id=42),
        )
    assert error.value.status_code == 404
    credit.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_free_plan_cannot_be_activated_through_public_subscription(monkeypatch):
    plan = SimpleNamespace(
        code="private-trial", name="Private trial", is_active=True, is_public=False,
        monthly_price_cents=0, annual_price_cents=0,
    )

    class Session:
        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: plan)

    @asynccontextmanager
    async def get_session():
        yield Session()

    monkeypatch.setattr(billing_sovereign.kodewaves_db_client, "get_session", get_session)
    credit = AsyncMock()
    monkeypatch.setattr(billing_sovereign.kodewaves_db_client, "add_minutes", credit)
    with pytest.raises(HTTPException) as error:
        await billing_sovereign.subscribe_to_plan(
            billing_sovereign.SubscribePlanRequest(plan_code="private-trial"),
            SimpleNamespace(selected_organization_id=42),
        )
    assert error.value.status_code == 404
    credit.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_paid_plan_cannot_create_a_self_service_checkout(monkeypatch):
    plan = SimpleNamespace(
        id="private-plan-id", code="private-enterprise", name="Private Enterprise",
        is_active=True, is_public=False, currency="INR", included_monthly_minutes=500,
        monthly_price_cents=100000, annual_price_cents=0,
    )

    class Session:
        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: plan)

    @asynccontextmanager
    async def get_session():
        yield Session()

    monkeypatch.setattr(payments.kodewaves_db_client, "get_session", get_session)
    monkeypatch.setattr(payments, "get_gateway_credentials", AsyncMock(return_value={}))
    with pytest.raises(HTTPException) as error:
        await payments.create_payment_order(
            payments.CreateOrderRequest(plan_code="private-enterprise"),
            SimpleNamespace(selected_organization_id=42, id=7, email="owner-assigned@example.test"),
        )
    assert error.value.status_code == 404


def test_payment_webhooks_reject_missing_signing_secrets(monkeypatch):
    monkeypatch.setattr(
        payments,
        "get_gateway_credentials",
        AsyncMock(return_value={"razorpay_webhook_secret": "", "stripe_webhook_secret": ""}),
    )
    app = FastAPI()
    app.include_router(payments.router)
    client = TestClient(app)
    assert client.post("/payments/razorpay/webhook", content=b"{}").status_code == 503
    assert client.post("/payments/stripe/webhook", content=b"{}").status_code == 503


@pytest.mark.asyncio
async def test_payment_configuration_does_not_advertise_sample_gateway_keys(monkeypatch):
    monkeypatch.setattr(payments, "get_gateway_credentials", AsyncMock(return_value={
        "razorpay_enabled": False, "razorpay_key_id": "", "stripe_enabled": False,
        "stripe_publishable_key": "",
    }))
    result = await payments.get_payment_configuration()
    assert result.razorpay_enabled is False
    assert result.razorpay_key_id is None
    assert result.stripe_enabled is False
    assert result.stripe_publishable_key is None


@pytest.mark.asyncio
@pytest.mark.parametrize("included_minutes", [0, 120])
async def test_paid_plan_payment_grants_minutes_and_one_finite_term(monkeypatch, included_minutes):
    plan = SimpleNamespace(
        code="pro", name="Pro", is_active=True,
        monthly_price_cents=2999, annual_price_cents=29900,
        currency="USD", included_monthly_minutes=included_minutes,
    )

    class Result:
        def scalar_one_or_none(self):
            return plan

    class Session:
        async def execute(self, _statement):
            return Result()

    @asynccontextmanager
    async def get_session():
        yield Session()

    added = AsyncMock(return_value=SimpleNamespace(credit_balance_minutes=120))
    monkeypatch.setattr(payments.kodewaves_db_client, "get_session", get_session)
    monkeypatch.setattr(payments.kodewaves_db_client, "add_minutes", added)
    monkeypatch.setattr(
        payments.kodewaves_db_client,
        "get_setting",
        AsyncMock(return_value={"plan_code": "pro", "expires_at": "2030-01-01T00:00:00+00:00"}),
    )

    response = await _grant_paid_order(
        {
            "amount": 29900,
            "currency": "USD",
            "metadata": {
                "organization_id": "42",
                "package_id": "",
                "plan_code": "pro",
                "billing_cycle": "annual",
            },
        },
        42,
        "stripe",
        "pi_123",
        "cs_123",
    )

    assert response.plan_code == "pro"
    assert response.plan_expires_at == "2030-01-01T00:00:00+00:00"
    added.assert_awaited_once()
    assert added.await_args.kwargs["minutes"] == included_minutes
    assert added.await_args.kwargs["plan_assignment"]["_term_days"] == 365


def test_unconfigured_provider_never_returns_a_fabricated_checkout_order(monkeypatch):
    package = SimpleNamespace(
        id="package-1", name="100 minutes", currency="INR", price_cents=2999,
        minutes=100, bonus_minutes=0, is_active=True,
    )

    class Result:
        def scalar_one_or_none(self):
            return package

    class Session:
        async def execute(self, _statement):
            return Result()

    @asynccontextmanager
    async def get_session():
        yield Session()

    monkeypatch.setattr(payments.kodewaves_db_client, "get_session", get_session)
    monkeypatch.setattr(payments, "get_gateway_credentials", AsyncMock(return_value={
        "razorpay_key_id": "", "razorpay_key_secret": "", "stripe_secret_key": "",
        "stripe_publishable_key": "",
    }))
    app = FastAPI()
    app.include_router(payments.router)
    app.dependency_overrides[payments.get_user] = lambda: SimpleNamespace(
        selected_organization_id=42, id=7, email="billing@example.test"
    )
    response = TestClient(app).post(
        "/payments/create-order", json={"package_id": "100 minutes", "gateway": "razorpay"}
    )
    assert response.status_code == 503
    assert "checkout is unavailable" in response.json()["detail"]


@pytest.mark.asyncio
async def test_stripe_paid_session_can_be_verified_without_trusting_browser_payment_id(monkeypatch):
    response_data = {
        "id": "cs_live_123", "payment_status": "paid", "payment_intent": "pi_live_456",
        "amount_total": 2999, "currency": "usd",
        "metadata": {"organization_id": "42", "package_id": "pkg-1", "plan_code": ""},
    }
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=response_data))
    original_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return original_client(transport=transport, **kwargs)

    monkeypatch.setattr(payments.httpx, "AsyncClient", client_factory)
    result = await _fetch_paid_order(
        VerifyPaymentRequest(gateway="stripe", order_id="cs_live_123"),
        {"stripe_secret_key": "sk_test"},
    )
    assert result["payment_id"] == "pi_live_456"
    assert result["amount"] == 2999
    assert result["currency"] == "USD"


@pytest.mark.asyncio
async def test_empty_public_catalog_does_not_create_sample_offers(monkeypatch):
    plans = AsyncMock(return_value=[])
    packages = AsyncMock(return_value=[])
    monkeypatch.setattr(billing_sovereign, "list_active_plans", plans)
    monkeypatch.setattr(billing_sovereign, "list_active_credit_packages", packages)
    assert await billing_sovereign.list_public_plans() == []
    assert await billing_sovereign.list_public_packages() == []
    plans.assert_awaited_once()
    packages.assert_awaited_once()


@pytest.mark.asyncio
async def test_public_plan_preserves_exact_price_and_actual_feature_grants(monkeypatch):
    record = SimpleNamespace(
        id="plan-1", name="Configured plan", code="configured", description="For this team",
        monthly_price_cents=2999, annual_price_cents=29900, currency="USD",
        included_monthly_minutes=100, max_agents=5, max_concurrent_calls=2, allow_user_byok=False,
        has_crm_access=True, has_appointments_access=False, has_forms_access=False,
        has_widget_access=True, is_active=True,
    )
    monkeypatch.setattr(billing_sovereign, "list_active_plans", AsyncMock(return_value=[record]))
    result = (await billing_sovereign.list_public_plans())[0]
    assert result.monthly_price_cents == 2999
    assert result.annual_price_cents == 29900
    assert result.currency == "USD"
    assert result.monthly_price_inr is None
    assert result.monthly_price_usd == 29.99
    assert result.max_agents == 5
    assert result.overage_rate_per_minute is None
    assert result.features == ["CRM access", "Web widgets"]
