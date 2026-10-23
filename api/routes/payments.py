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
    OrganizationWalletModel,
    SaaSPlanModel,
    WalletLedgerModel,
)
from api.db.models import UserModel
from api.services.auth.depends import get_user
from api.services.payment_receipts import PaymentReceiptError, verify_payment_receipt

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


def verify_stripe_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify a fresh Stripe v1 signature over the unmodified request body."""
    if not secret or not signature:
        return False
    try:
        fields = [part.split("=", 1) for part in signature.split(",") if "=" in part]
        timestamps = [value for key, value in fields if key == "t"]
        if len(timestamps) != 1 or abs(datetime.now(UTC).timestamp() - int(timestamps[0])) > 300:
            return False
        expected = hmac.new(secret.encode(), timestamps[0].encode() + b"." + body, hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(expected, value) for key, value in fields if key == "v1")
    except (TypeError, ValueError, UnicodeError):
        return False


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
    payment_id: str
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
    gateway = req.gateway.lower()
    if gateway not in {"razorpay", "stripe"}:
        raise HTTPException(status_code=400, detail="Unsupported payment gateway")
    if not creds.get(gateway + "_enabled"):
        raise HTTPException(status_code=503, detail="Payment gateway is not configured")
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
            if not package:
                raise HTTPException(status_code=404, detail="Credit package not found")
            item_title = package.name
            currency = package.currency or currency
            # Admin prices are already stored in minor units (paise/cents).
            amount_units = package.price_cents
            minutes_to_credit = package.minutes + (package.bonus_minutes or 0)
            package_ref = str(package.id)

        # Case B: SaaS Subscription Plan
        elif req.plan_id or req.plan_code:
            query = select(SaaSPlanModel)
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
            if not plan:
                raise HTTPException(status_code=404, detail="SaaS Plan not found")
            item_title = f"{plan.name} Plan ({req.billing_cycle})"
            currency = plan.currency or currency
            base_cents = plan.annual_price_cents if req.billing_cycle == "annual" else plan.monthly_price_cents
            amount_units = base_cents
            minutes_to_credit = plan.included_monthly_minutes
            plan_ref = plan.code
        else:
            raise HTTPException(status_code=400, detail="Must provide either package_id or plan_id/plan_code")

    notes = {
        "organization_id": str(org_id),
        "user_id": str(user.id),
        "user_email": user.email or "",
        "item_title": item_title,
        "minutes": str(minutes_to_credit),
        "package_id": package_ref or "",
        "plan_code": plan_ref or "",
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

        raise HTTPException(status_code=502, detail="Payment provider could not create an order")

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
                            "success_url": "https://app.kodewaves.in/billing-sovereign?payment=success&session_id={CHECKOUT_SESSION_ID}",
                            "cancel_url": "https://app.kodewaves.in/billing-sovereign?payment=cancelled",
                            "client_reference_id": f"kw_{org_id}",
                            "metadata[organization_id]": str(org_id),
                            "metadata[minutes]": str(minutes_to_credit),
                            "metadata[package_id]": package_ref or "",
                            "metadata[plan_code]": plan_ref or "",
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

        raise HTTPException(status_code=502, detail="Payment provider could not create a checkout")

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

    # Signature verification for Razorpay
    if req.gateway.lower() == "razorpay":
        secret = creds.get("razorpay_key_secret")
        if not secret:
            raise HTTPException(status_code=400, detail="Razorpay gateway is not configured on this platform")
        if not req.signature:
            raise HTTPException(status_code=400, detail="Razorpay signature is required for payment verification")
        if not verify_razorpay_signature(req.order_id, req.payment_id, req.signature, secret):
            raise HTTPException(status_code=400, detail="Invalid Razorpay payment signature")

    try:
        receipt = await verify_payment_receipt(
            gateway=req.gateway.lower(), order_id=req.order_id, payment_id=req.payment_id,
            organization_id=org_id, credentials=creds,
        )
    except PaymentReceiptError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    minutes_to_add = receipt.minutes
    assigned_plan_code = receipt.plan_code

    # Credit minutes to organization wallet
    wallet = await kodewaves_db_client.add_minutes(
        organization_id=org_id,
        minutes=minutes_to_add,
        reason="plan_subscription" if assigned_plan_code else "credit_purchase",
        reference_id=receipt.reference_id,
        notes=f"Payment verified via {req.gateway.upper()} (Order: {req.order_id})",
    )

    if assigned_plan_code:
        await kodewaves_db_client.set_setting(
            f"org_plan_{org_id}",
            {"plan_code": assigned_plan_code, "updated_at": datetime.now(UTC).isoformat()},
            category="plan",
        )

    logger.info(
        f"[Payments] Credited {minutes_to_add} minutes to org {org_id}. "
        f"New balance: {wallet.credit_balance_minutes}. Ref: {req.payment_id}"
    )

    return VerifyPaymentResponse(
        success=True,
        message=f"Payment of {minutes_to_add} voice minutes confirmed and added to your balance.",
        minutes_added=minutes_to_add,
        new_wallet_balance=wallet.credit_balance_minutes,
        plan_code=assigned_plan_code,
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

    if not secret:
        raise HTTPException(status_code=503, detail="Razorpay webhook is not configured")
    if not x_razorpay_signature or not verify_razorpay_webhook_signature(body, x_razorpay_signature, secret):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        event = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = event.get("event")
    logger.info(f"[Payments] Razorpay webhook received: {event_type}")

    if event_type in ("payment.captured", "order.paid"):
        payload = event.get("payload", {})
        payment_entity = payload.get("payment", {}).get("entity", {})
        notes = payment_entity.get("notes", {})

        org_id_str = notes.get("organization_id")
        minutes_str = notes.get("minutes")
        payment_id = payment_entity.get("id")

        if org_id_str and minutes_str:
            try:
                org_id = int(org_id_str)
                minutes = int(minutes_str)
                if org_id <= 0 or minutes <= 0 or not payment_id:
                    raise ValueError("Invalid payment entitlement")
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Invalid payment entitlement") from None
            try:
                await kodewaves_db_client.add_minutes(
                    organization_id=org_id,
                    minutes=minutes,
                    reason="credit_purchase",
                    reference_id=payment_id,
                    notes=f"Razorpay webhook: {event_type}",
                )
                logger.info(f"[Payments] Webhook credited {minutes} minutes to Org #{org_id}")
            except Exception as e:
                logger.error(f"[Payments] Webhook credit error: {e}")
                raise HTTPException(status_code=503, detail="Payment credit could not be recorded") from e

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

    if not webhook_secret:
        raise HTTPException(status_code=503, detail="Stripe webhook is not configured")
    if not stripe_signature or not verify_stripe_webhook_signature(body, stripe_signature, webhook_secret):
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature")

    try:
        event = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = event.get("type")
    logger.info(f"[Payments] Stripe webhook received: {event_type}")

    # These are one-time Checkout purchases. Recurring invoice entitlements
    # need their own subscription reconciliation rather than another top-up.
    if event_type in ("checkout.session.completed", "payment_intent.succeeded"):
        data_obj = event.get("data", {}).get("object", {})
        metadata = data_obj.get("metadata", {})
        org_id_str = metadata.get("organization_id")
        minutes_str = metadata.get("minutes")
        # Checkout redirects identify a session, while verification and payment
        # events identify its PaymentIntent. Use one credit reference for both.
        payment_id = data_obj.get("id") if event_type == "payment_intent.succeeded" else data_obj.get("payment_intent")
        if isinstance(payment_id, dict):
            payment_id = payment_id.get("id")
        paid = (
            data_obj.get("status") == "succeeded" if event_type == "payment_intent.succeeded"
            else data_obj.get("payment_status") == "paid"
        )
        if not paid:
            return {"status": "ok"}

        if org_id_str and minutes_str:
            try:
                org_id = int(org_id_str)
                minutes = int(minutes_str)
                if org_id <= 0 or minutes <= 0 or not isinstance(payment_id, str) or not payment_id:
                    raise ValueError("Invalid payment entitlement")
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Invalid payment entitlement") from None
            try:
                await kodewaves_db_client.add_minutes(
                    organization_id=org_id,
                    minutes=minutes,
                    reason="credit_purchase",
                    reference_id=payment_id,
                    notes=f"Stripe webhook: {event_type}",
                )
                logger.info(f"[Payments] Stripe webhook credited {minutes} minutes to Org #{org_id}")
            except Exception as e:
                logger.error(f"[Payments] Stripe credit error: {e}")
                raise HTTPException(status_code=503, detail="Payment credit could not be recorded") from e

    return {"status": "ok"}
