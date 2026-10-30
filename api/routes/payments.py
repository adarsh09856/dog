import hashlib
import hmac
import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import (
    CreditPackageModel,
    SaaSPlanModel,
)
from api.db.models import UserModel
from api.constants import UI_APP_URL
from api.services.auth.depends import get_user

router = APIRouter(prefix="/payments", tags=["payments"])


# -----------------------------------------------------------------------------
# Gateway Helper Utilities
# -----------------------------------------------------------------------------
async def get_gateway_credentials() -> Dict[str, Any]:
    """Retrieve Razorpay and Stripe configuration from DB or environment."""
    saved_gateways = await kodewaves_db_client.get_setting("gateways") or {}

    razorpay_key_id = saved_gateways.get("razorpay_key_id") or os.getenv("RAZORPAY_KEY_ID", "")
    razorpay_key_secret = saved_gateways.get("razorpay_key_secret") or os.getenv("RAZORPAY_KEY_SECRET", "")
    razorpay_webhook_secret = saved_gateways.get("razorpay_webhook_secret") or os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

    stripe_publishable_key = saved_gateways.get("stripe_publishable_key") or os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    stripe_secret_key = saved_gateways.get("stripe_secret_key") or os.getenv("STRIPE_SECRET_KEY", "")
    stripe_webhook_secret = saved_gateways.get("stripe_webhook_secret") or os.getenv("STRIPE_WEBHOOK_SECRET", "")

    return {
        "razorpay_key_id": razorpay_key_id,
        "razorpay_key_secret": razorpay_key_secret,
        "razorpay_webhook_secret": razorpay_webhook_secret,
        "razorpay_enabled": bool(razorpay_key_id and razorpay_key_secret),
        "stripe_publishable_key": stripe_publishable_key,
        "stripe_secret_key": stripe_secret_key,
        "stripe_webhook_secret": stripe_webhook_secret,
        "stripe_enabled": bool(stripe_publishable_key and stripe_secret_key),
    }


def verify_razorpay_signature(order_id: str, payment_id: str, signature: str, secret: str) -> bool:
    """Validate Razorpay HMAC-SHA256 signature."""
    if not secret:
        return False
    try:
        msg = f"{order_id}|{payment_id}".encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception as e:
        logger.error(f"[Payments] Razorpay signature verification error: {e}")
        return False


def verify_razorpay_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    """Validate Razorpay Webhook HMAC-SHA256 signature."""
    if not secret:
        return False
    try:
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception as e:
        logger.error(f"[Payments] Razorpay webhook signature error: {e}")
        return False


def _minor_units_to_gateway_units(amount: int) -> int:
    """Gateway APIs accept the exact paise/cents integer stored by the catalog."""
    return max(0, int(amount or 0))


def _require_purchasable_package(package) -> None:
    if package.price_cents <= 0 or package.minutes <= 0 or (package.bonus_minutes or 0) < 0:
        raise HTTPException(status_code=400, detail="This credit package is not available for purchase")


def _plan_price_for_checkout(plan: SaaSPlanModel, billing_cycle: str) -> int:
    if billing_cycle not in {"monthly", "annual"}:
        raise HTTPException(status_code=422, detail="Billing cycle must be monthly or annual")
    amount = plan.annual_price_cents if billing_cycle == "annual" else plan.monthly_price_cents
    if amount <= 0:
        if billing_cycle == "monthly" and plan.annual_price_cents > 0:
            raise HTTPException(status_code=400, detail="This plan is available only with annual billing")
        raise HTTPException(status_code=400, detail="This plan has no paid price to check out")
    return int(amount)


async def _fetch_paid_order(req: "VerifyPaymentRequest", creds: Dict[str, Any]) -> dict[str, Any]:
    """Fetch and validate the authoritative gateway order and its purchased item."""
    gateway = req.gateway.lower()
    async with httpx.AsyncClient(timeout=10.0) as client:
        if gateway == "razorpay":
            key_id, secret = creds.get("razorpay_key_id"), creds.get("razorpay_key_secret")
            if not key_id or not secret:
                raise HTTPException(status_code=400, detail="Razorpay gateway is not configured")
            order_response = await client.get(
                f"https://api.razorpay.com/v1/orders/{req.order_id}", auth=(key_id, secret)
            )
            if not req.payment_id:
                raise HTTPException(status_code=400, detail="Razorpay payment ID is required")
            payment_response = await client.get(
                f"https://api.razorpay.com/v1/payments/{req.payment_id}", auth=(key_id, secret)
            )
            if order_response.status_code != 200 or payment_response.status_code != 200:
                raise HTTPException(status_code=402, detail="Payment order could not be verified")
            order = order_response.json()
            payment = payment_response.json()
            if (
                order.get("id") != req.order_id
                or order.get("status") != "paid"
                or payment is None
                or payment.get("order_id") != req.order_id
                or payment.get("status") != "captured"
                or payment.get("amount") != order.get("amount")
                or payment.get("currency") != order.get("currency")
            ):
                raise HTTPException(status_code=402, detail="Payment is not captured for this order")
            return {
                "amount": order["amount"], "currency": order["currency"],
                "metadata": order.get("notes", {}),
                "payment_id": payment.get("id"),
            }

        if gateway == "stripe":
            secret = creds.get("stripe_secret_key")
            if not secret:
                raise HTTPException(status_code=400, detail="Stripe gateway is not configured")
            response = await client.get(
                f"https://api.stripe.com/v1/checkout/sessions/{req.order_id}",
                headers={"Authorization": f"Bearer {secret}"},
            )
            if response.status_code != 200:
                raise HTTPException(status_code=402, detail="Payment session could not be verified")
            session = response.json()
            if (
                session.get("id") != req.order_id
                or session.get("payment_status") != "paid"
                or not session.get("payment_intent")
                or (req.payment_id and session.get("payment_intent") != req.payment_id)
            ):
                raise HTTPException(status_code=402, detail="Payment is not complete for this session")
            return {
                "amount": session.get("amount_total"),
                "currency": str(session.get("currency", "")).upper(),
                "metadata": session.get("metadata", {}),
                "payment_id": session.get("payment_intent"),
            }

    raise HTTPException(status_code=400, detail=f"Unsupported gateway '{req.gateway}'")


def _validate_order_metadata(metadata: dict[str, Any], organization_id: int) -> tuple[str, str, str]:
    """Require the paid order to name exactly one item owned by this organization."""
    if str(metadata.get("organization_id")) != str(organization_id):
        raise HTTPException(status_code=403, detail="Payment order belongs to another organization")
    package_id = str(metadata.get("package_id") or "")
    plan_code = str(metadata.get("plan_code") or "")
    if bool(package_id) == bool(plan_code):
        raise HTTPException(status_code=400, detail="Payment order has an invalid item reference")
    billing_cycle = str(metadata.get("billing_cycle") or "monthly")
    if billing_cycle not in {"monthly", "annual"}:
        raise HTTPException(status_code=400, detail="Payment order has an invalid billing cycle")
    return package_id, plan_code, billing_cycle


def _order_organization_id(metadata: dict[str, Any]) -> int:
    try:
        organization_id = int(metadata.get("organization_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Payment order has an invalid organization reference") from None
    if organization_id <= 0:
        raise HTTPException(status_code=400, detail="Payment order has an invalid organization reference")
    return organization_id


def _paid_plan_assignment(plan: SaaSPlanModel, billing_cycle: str) -> dict[str, Any]:
    """Describe a finite, manually renewable term for the atomic wallet grant."""
    return {
        "plan_code": plan.code,
        "plan_name": plan.name,
        "billing_cycle": billing_cycle,
        "_term_days": 365 if billing_cycle == "annual" else 30,
    }


# -----------------------------------------------------------------------------
# Request & Response Schemas
# -----------------------------------------------------------------------------
class PaymentConfigResponse(BaseModel):
    razorpay_enabled: bool
    razorpay_key_id: Optional[str] = None
    stripe_enabled: bool
    stripe_publishable_key: Optional[str] = None
    default_currency: str = "INR"


class CreateOrderRequest(BaseModel):
    package_id: Optional[str] = None
    plan_id: Optional[str] = None
    plan_code: Optional[str] = None
    gateway: str = "razorpay" # "razorpay" or "stripe"
    currency: Optional[str] = None # "INR" or "USD"
    billing_cycle: Optional[str] = "monthly" # "monthly" or "annual"


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    gateway: str
    key_id: Optional[str] = None
    checkout_url: Optional[str] = None
    notes: Dict[str, Any] = {}


class VerifyPaymentRequest(BaseModel):
    gateway: str = "razorpay"
    order_id: str
    payment_id: Optional[str] = None
    signature: Optional[str] = None
    package_id: Optional[str] = None
    plan_id: Optional[str] = None
    plan_code: Optional[str] = None


class VerifyPaymentResponse(BaseModel):
    success: bool
    message: str
    minutes_added: int
    new_wallet_balance: int
    plan_code: Optional[str] = None
    plan_expires_at: Optional[str] = None


async def _grant_paid_order(
    paid_order: dict[str, Any], organization_id: int, gateway: str, payment_id: str, order_id: str
) -> VerifyPaymentResponse:
    """Grant the catalog item from a provider-verified payment, idempotently."""
    package_ref, plan_ref, billing_cycle = _validate_order_metadata(
        paid_order.get("metadata") or {}, organization_id
    )
    minutes_to_add = 0
    assigned_plan_code = None
    plan_assignment = None
    async with kodewaves_db_client.get_session() as session:
        if package_ref:
            try:
                package_identity = uuid.UUID(package_ref)
                stmt = select(CreditPackageModel).where(CreditPackageModel.id == package_identity)
            except ValueError:
                stmt = select(CreditPackageModel).where(CreditPackageModel.name == package_ref)
            package = (await session.execute(stmt)).scalar_one_or_none()
            if not package or not package.is_active:
                raise HTTPException(status_code=404, detail="Paid credit package is no longer available")
            if package.currency != paid_order["currency"] or package.price_cents != paid_order["amount"]:
                raise HTTPException(status_code=409, detail="Paid package price no longer matches its catalog price")
            minutes_to_add = package.minutes + (package.bonus_minutes or 0)
        if plan_ref:
            plan = (await session.execute(
                select(SaaSPlanModel).where(SaaSPlanModel.code == plan_ref)
            )).scalar_one_or_none()
            if not plan or not plan.is_active:
                raise HTTPException(status_code=404, detail="Paid plan is no longer available")
            expected_amount = plan.annual_price_cents if billing_cycle == "annual" else plan.monthly_price_cents
            if plan.currency != paid_order["currency"] or expected_amount != paid_order["amount"]:
                raise HTTPException(status_code=409, detail="Paid plan price no longer matches its catalog price")
            assigned_plan_code = plan.code
            minutes_to_add = plan.included_monthly_minutes
            plan_assignment = _paid_plan_assignment(plan, billing_cycle)
    if minutes_to_add < 0 or (minutes_to_add == 0 and not plan_assignment):
        raise HTTPException(status_code=400, detail="Paid item has no minutes to grant")
    wallet = await kodewaves_db_client.add_minutes(
        organization_id=organization_id,
        minutes=minutes_to_add,
        reason="credit_purchase" if package_ref else "plan_subscription",
        reference_id=payment_id or order_id,
        notes=f"Payment verified via {gateway.upper()} (Order: {order_id})",
        plan_assignment=plan_assignment,
    )
    persisted_plan = (
        await kodewaves_db_client.get_setting(f"org_plan_{organization_id}")
        if assigned_plan_code
        else None
    )
    return VerifyPaymentResponse(
        success=True,
        message=f"Payment of {minutes_to_add} voice minutes confirmed and added to your balance.",
        minutes_added=minutes_to_add,
        new_wallet_balance=wallet.credit_balance_minutes,
        plan_code=assigned_plan_code,
        plan_expires_at=(
            persisted_plan.get("expires_at")
            if isinstance(persisted_plan, dict)
            else None
        ),
    )


# -----------------------------------------------------------------------------
# 1. Config Endpoint
# -----------------------------------------------------------------------------
@router.get("/config", response_model=PaymentConfigResponse)
async def get_payment_configuration():
    """Retrieve public payment gateway parameters for checkout components."""
    creds = await get_gateway_credentials()
    return PaymentConfigResponse(
        razorpay_enabled=creds["razorpay_enabled"],
        razorpay_key_id=creds["razorpay_key_id"] or None,
        stripe_enabled=creds["stripe_enabled"],
        stripe_publishable_key=creds["stripe_publishable_key"] or None,
        default_currency="INR",
    )


# -----------------------------------------------------------------------------
# 2. Create Order / Checkout Session
# -----------------------------------------------------------------------------
@router.post("/create-order", response_model=CreateOrderResponse)
async def create_payment_order(req: CreateOrderRequest, user: UserModel = Depends(get_user)):
    """Create a Razorpay Order or Stripe Checkout Session for plans or minute packs."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no selected organization")

    creds = await get_gateway_credentials()
    item_title = ""
    amount_units = 0 # in paise (INR) or cents (USD)
    currency = req.currency or "INR"
    minutes_to_credit = 0
    package_ref = None
    plan_ref = None

    async with kodewaves_db_client.get_session() as session:
        # Case A: Minute Top-up Package
        if req.package_id:
            try:
                pkg_uuid = uuid.UUID(req.package_id)
                stmt = select(CreditPackageModel).where(CreditPackageModel.id == pkg_uuid)
            except ValueError:
                stmt = select(CreditPackageModel).where(CreditPackageModel.name == req.package_id)
            pkg_res = await session.execute(stmt)
            package = pkg_res.scalar_one_or_none()
            if not package or not package.is_active:
                raise HTTPException(status_code=404, detail="Active credit package not found")
            _require_purchasable_package(package)
            item_title = package.name
            currency = package.currency or currency
            amount_units = _minor_units_to_gateway_units(package.price_cents)
            minutes_to_credit = package.minutes + (package.bonus_minutes or 0)
            package_ref = str(package.id)

        # Case B: SaaS Subscription Plan
        elif req.plan_id or req.plan_code:
            query = select(SaaSPlanModel).where(SaaSPlanModel.is_public.is_(True))
            if req.plan_id:
                try:
                    p_uuid = uuid.UUID(req.plan_id)
                    query = query.where(SaaSPlanModel.id == p_uuid)
                except ValueError:
                    query = query.where(SaaSPlanModel.code == req.plan_id)
            elif req.plan_code:
                query = query.where(SaaSPlanModel.code == req.plan_code)

            plan_res = await session.execute(query)
            plan = plan_res.scalar_one_or_none()
            if not plan or not plan.is_active or not plan.is_public:
                raise HTTPException(status_code=404, detail="Active SaaS plan not found")
            item_title = f"{plan.name} Plan ({req.billing_cycle})"
            currency = plan.currency or currency
            base_cents = _plan_price_for_checkout(plan, req.billing_cycle or "monthly")
            amount_units = _minor_units_to_gateway_units(base_cents)
            minutes_to_credit = plan.included_monthly_minutes
            plan_ref = plan.code
        else:
            raise HTTPException(status_code=400, detail="Must provide either package_id or plan_id/plan_code")

    if amount_units <= 0:
        raise HTTPException(status_code=400, detail="Checkout amount must be greater than zero")

    notes = {
        "organization_id": str(org_id),
        "user_id": str(user.id),
        "user_email": user.email or "",
        "item_title": item_title,
        "minutes": str(minutes_to_credit),
        "package_id": package_ref or "",
        "plan_code": plan_ref or "",
        "billing_cycle": req.billing_cycle or "monthly",
    }

    # Gateway Execution
    if req.gateway.lower() == "razorpay":
        key_id = creds["razorpay_key_id"]
        key_secret = creds["razorpay_key_secret"]

        if key_id and key_secret:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    rzp_res = await client.post(
                        "https://api.razorpay.com/v1/orders",
                        auth=(key_id, key_secret),
                        json={
                            "amount": amount_units,
                            "currency": currency,
                            "receipt": f"kw_{org_id}_{int(datetime.now(UTC).timestamp())}",
                            "notes": notes,
                        },
                    )
                    if rzp_res.status_code in (200, 201):
                        data = rzp_res.json()
                        return CreateOrderResponse(
                            order_id=data["id"],
                            amount=data["amount"],
                            currency=data["currency"],
                            gateway="razorpay",
                            key_id=key_id,
                            notes=notes,
                        )
                    else:
                        logger.warning(f"[Payments] Razorpay order creation failed: {rzp_res.text}")
            except Exception as e:
                logger.error(f"[Payments] Razorpay connection error: {e}")

        raise HTTPException(
            status_code=503,
            detail="Razorpay checkout is unavailable; configure valid gateway credentials and retry",
        )

    elif req.gateway.lower() == "stripe":
        stripe_sec = creds["stripe_secret_key"]
        if stripe_sec:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    stripe_res = await client.post(
                        "https://api.stripe.com/v1/checkout/sessions",
                        headers={"Authorization": f"Bearer {stripe_sec}"},
                        data={
                            "payment_method_types[]": "card",
                            "line_items[0][price_data][currency]": currency.lower(),
                            "line_items[0][price_data][product_data][name]": item_title,
                            "line_items[0][price_data][unit_amount]": amount_units,
                            "line_items[0][quantity]": 1,
                            "mode": "payment",
                            "success_url": f"{str(UI_APP_URL).rstrip('/')}/billing-sovereign?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
                            "cancel_url": f"{str(UI_APP_URL).rstrip('/')}/billing-sovereign?payment=cancelled",
                            "client_reference_id": f"kw_{org_id}",
                            "metadata[organization_id]": str(org_id),
                            "metadata[minutes]": str(minutes_to_credit),
                            "metadata[package_id]": package_ref or "",
                            "metadata[plan_code]": plan_ref or "",
                            "metadata[billing_cycle]": req.billing_cycle or "monthly",
                        },
                    )
                    if stripe_res.status_code in (200, 201):
                        data = stripe_res.json()
                        return CreateOrderResponse(
                            order_id=data["id"],
                            amount=amount_units,
                            currency=currency,
                            gateway="stripe",
                            key_id=creds["stripe_publishable_key"],
                            checkout_url=data.get("url"),
                            notes=notes,
                        )
            except Exception as e:
                logger.error(f"[Payments] Stripe session creation error: {e}")

        raise HTTPException(
            status_code=503,
            detail="Stripe checkout is unavailable; configure valid gateway credentials and retry",
        )

    raise HTTPException(status_code=400, detail=f"Unsupported gateway '{req.gateway}'")


# -----------------------------------------------------------------------------
# 3. Client Verification Endpoint
# -----------------------------------------------------------------------------
@router.post("/verify", response_model=VerifyPaymentResponse)
async def verify_payment(req: VerifyPaymentRequest, user: UserModel = Depends(get_user)):
    """Verify payment receipt and credit voice minutes to the organization wallet."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no selected organization")

    creds = await get_gateway_credentials()

    # Check Razorpay's callback HMAC, then independently retrieve the paid
    # order and payment so caller-supplied item IDs cannot change the grant.
    if req.gateway.lower() == "razorpay":
        secret = creds.get("razorpay_key_secret")
        if not secret:
            raise HTTPException(status_code=400, detail="Razorpay gateway is not configured on this platform")
        if not req.payment_id:
            raise HTTPException(status_code=400, detail="Razorpay payment ID is required")
        if not req.signature:
            raise HTTPException(status_code=400, detail="Razorpay signature is required for payment verification")
        if not verify_razorpay_signature(req.order_id, req.payment_id, req.signature, secret):
            raise HTTPException(status_code=400, detail="Invalid Razorpay payment signature")

    paid_order = await _fetch_paid_order(req, creds)
    package_ref, plan_ref, billing_cycle = _validate_order_metadata(
        paid_order["metadata"], org_id
    )
    if req.package_id and req.package_id != package_ref:
        raise HTTPException(status_code=400, detail="Package does not match the paid order")
    if (req.plan_id or req.plan_code) and (req.plan_code or req.plan_id) != plan_ref:
        raise HTTPException(status_code=400, detail="Plan does not match the paid order")
    return await _grant_paid_order(
        paid_order,
        org_id,
        req.gateway.lower(),
        paid_order.get("payment_id") or req.payment_id or req.order_id,
        req.order_id,
    )


# -----------------------------------------------------------------------------
# 4. Razorpay Webhook Handler
# -----------------------------------------------------------------------------
@router.post("/razorpay/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature"),
):
    """Handle incoming Razorpay server-to-server webhook events."""
    body = await request.body()
    creds = await get_gateway_credentials()
    secret = creds["razorpay_webhook_secret"]

    if not secret or not x_razorpay_signature:
        raise HTTPException(status_code=400, detail="Razorpay webhook signature is not configured or missing")
    if not verify_razorpay_webhook_signature(body, x_razorpay_signature, secret):
        logger.warning("[Payments] Invalid Razorpay webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        event = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = event.get("event")
    logger.info(f"[Payments] Razorpay webhook received: {event_type}")

    if event_type == "payment.captured":
        payment = event.get("payload", {}).get("payment", {}).get("entity", {})
        order_id, payment_id = payment.get("order_id"), payment.get("id")
        if not order_id or not payment_id:
            raise HTTPException(status_code=400, detail="Captured payment is missing its order reference")
        paid = await _fetch_paid_order(
            VerifyPaymentRequest(gateway="razorpay", order_id=order_id, payment_id=payment_id),
            creds,
        )
        organization_id = _order_organization_id(paid["metadata"])
        await _grant_paid_order(paid, organization_id, "razorpay", payment_id, order_id)

    return {"status": "ok"}


# -----------------------------------------------------------------------------
# 5. Stripe Webhook Handler
# -----------------------------------------------------------------------------
@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
):
    """Handle incoming Stripe server-to-server webhook events."""
    body = await request.body()
    creds = await get_gateway_credentials()
    webhook_secret = creds["stripe_webhook_secret"]

    if not webhook_secret or not stripe_signature:
        raise HTTPException(status_code=400, detail="Stripe webhook signature is not configured or missing")
    try:
        parts = [part.split("=", 1) for part in stripe_signature.split(",") if "=" in part]
        timestamp = next((value for key, value in parts if key == "t"), "")
        signatures = [value for key, value in parts if key == "v1"]
        if not timestamp or abs(int(datetime.now(UTC).timestamp()) - int(timestamp)) > 300:
            raise HTTPException(status_code=400, detail="Stripe webhook timestamp is invalid or expired")
        signed_payload = f"{timestamp}.".encode("utf-8") + body
        computed = hmac.new(webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(computed, candidate) for candidate in signatures):
            raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[Payments] Stripe signature check error: {e}")
        raise HTTPException(status_code=400, detail="Error validating Stripe webhook signature")

    try:
        event = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = event.get("type")
    logger.info(f"[Payments] Stripe webhook received: {event_type}")

    if event_type == "checkout.session.completed":
        data_obj = event.get("data", {}).get("object", {})
        order_id, payment_id = data_obj.get("id"), data_obj.get("payment_intent")
        if not order_id or not payment_id:
            raise HTTPException(status_code=400, detail="Completed Stripe session is missing its payment reference")
        paid = await _fetch_paid_order(
            VerifyPaymentRequest(gateway="stripe", order_id=order_id, payment_id=payment_id), creds
        )
        organization_id = _order_organization_id(paid["metadata"])
        await _grant_paid_order(paid, organization_id, "stripe", payment_id, order_id)

    return {"status": "ok"}
