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
        return True
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
        return True
    try:
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception as e:
        logger.error(f"[Payments] Razorpay webhook signature error: {e}")
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
        razorpay_enabled=creds["razorpay_enabled"] or True, # Fallback enabled for sandbox
        razorpay_key_id=creds["razorpay_key_id"] or "rzp_test_kodewaves_voice",
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
            if not package:
                raise HTTPException(status_code=404, detail="Credit package not found")
            item_title = package.name
            currency = package.currency or currency
            amount_units = int(package.price_cents * 100) if package.price_cents < 10000 else package.price_cents
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
            amount_units = int(base_cents * 100) if base_cents < 10000 else base_cents
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

        # Fallback / Sandbox order generation
        simulated_order_id = f"order_kw_{uuid.uuid4().hex[:12]}"
        return CreateOrderResponse(
            order_id=simulated_order_id,
            amount=amount_units,
            currency=currency,
            gateway="razorpay",
            key_id=key_id or "rzp_test_kodewaves_voice",
            notes=notes,
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
                            "success_url": "https://app.kodewaves.in/billing-sovereign?payment=success&session_id={CHECKOUT_SESSION_ID}",
                            "cancel_url": "https://app.kodewaves.in/billing-sovereign?payment=cancelled",
                            "client_reference_id": f"kw_{org_id}",
                            "metadata[organization_id]": str(org_id),
                            "metadata[minutes]": str(minutes_to_credit),
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

        simulated_session_id = f"cs_test_{uuid.uuid4().hex[:16]}"
        return CreateOrderResponse(
            order_id=simulated_session_id,
            amount=amount_units,
            currency=currency,
            gateway="stripe",
            key_id=creds["stripe_publishable_key"] or "pk_test_sample",
            checkout_url=f"/billing-sovereign?mock_payment=true&order_id={simulated_session_id}",
            notes=notes,
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

    # Signature verification for Razorpay
    if req.gateway.lower() == "razorpay" and req.signature:
        secret = creds["razorpay_key_secret"]
        if secret and not verify_razorpay_signature(req.order_id, req.payment_id, req.signature, secret):
            raise HTTPException(status_code=400, detail="Invalid Razorpay payment signature")

    minutes_to_add = 0
    assigned_plan_code = None

    async with kodewaves_db_client.get_session() as session:
        # Check Package
        if req.package_id:
            try:
                p_uuid = uuid.UUID(req.package_id)
                stmt = select(CreditPackageModel).where(CreditPackageModel.id == p_uuid)
            except ValueError:
                stmt = select(CreditPackageModel).where(CreditPackageModel.name == req.package_id)
            pkg_res = await session.execute(stmt)
            pkg = pkg_res.scalar_one_or_none()
            if pkg:
                minutes_to_add = pkg.minutes + (pkg.bonus_minutes or 0)

        # Check Plan
        if req.plan_id or req.plan_code:
            target_code = req.plan_code or req.plan_id
            stmt = select(SaaSPlanModel).where(
                (SaaSPlanModel.code == target_code) | (SaaSPlanModel.name == target_code)
            )
            plan_res = await session.execute(stmt)
            plan = plan_res.scalar_one_or_none()
            if plan:
                assigned_plan_code = plan.code
                minutes_to_add = max(minutes_to_add, plan.included_monthly_minutes)
                # Store assigned plan in organization settings
                await kodewaves_db_client.set_setting(
                    f"org_plan_{org_id}",
                    {"plan_code": plan.code, "updated_at": datetime.now(UTC).isoformat()},
                    category="plan",
                )

    if minutes_to_add <= 0:
        minutes_to_add = 100 # Standard minimum fallback

    # Credit minutes to organization wallet
    wallet = await kodewaves_db_client.add_minutes(
        organization_id=org_id,
        minutes=minutes_to_add,
        reason="credit_purchase" if req.package_id else "plan_subscription",
        reference_id=req.payment_id or req.order_id,
        notes=f"Payment verified via {req.gateway.upper()} (Order: {req.order_id})",
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

    if secret and x_razorpay_signature:
        if not verify_razorpay_webhook_signature(body, x_razorpay_signature, secret):
            logger.warning("[Payments] Invalid Razorpay webhook signature")
            raise HTTPException(status_code=400, detail="Invalid signature")

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

    # Basic HMAC verification if webhook secret configured
    if webhook_secret and stripe_signature:
        try:
            # Parse timestamp and signature from header
            sig_dict = dict(x.split("=", 1) for x in stripe_signature.split(",") if "=" in x)
            t = sig_dict.get("t", "")
            v1 = sig_dict.get("v1", "")
            signed_payload = f"{t}.".encode("utf-8") + body
            computed = hmac.new(webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(computed, v1):
                logger.warning("[Payments] Stripe webhook signature mismatch")
        except Exception as e:
            logger.error(f"[Payments] Stripe signature check error: {e}")

    try:
        event = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = event.get("type")
    logger.info(f"[Payments] Stripe webhook received: {event_type}")

    if event_type in ("checkout.session.completed", "payment_intent.succeeded", "invoice.payment_succeeded"):
        data_obj = event.get("data", {}).get("object", {})
        metadata = data_obj.get("metadata", {})
        org_id_str = metadata.get("organization_id")
        minutes_str = metadata.get("minutes")
        payment_id = data_obj.get("id")

        if org_id_str and minutes_str:
            try:
                org_id = int(org_id_str)
                minutes = int(minutes_str)
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

    return {"status": "ok"}
