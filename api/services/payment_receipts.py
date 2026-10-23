"""Resolve paid checkout entitlements from the provider, never client choices."""
from dataclasses import dataclass
from urllib.parse import quote

import httpx


class PaymentReceiptError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class VerifiedPaymentReceipt:
    minutes: int
    reference_id: str
    plan_code: str | None


def _entitlement(metadata: dict, organization_id: int, reference: str) -> VerifiedPaymentReceipt:
    try:
        owner = int(metadata['organization_id'])
        raw_minutes = str(metadata['minutes'])
        if not raw_minutes.isascii() or not raw_minutes.isdecimal():
            raise ValueError
        minutes = int(raw_minutes)
    except (KeyError, TypeError, ValueError):
        raise PaymentReceiptError('Payment has no valid purchased entitlement') from None
    if owner != organization_id:
        raise PaymentReceiptError('Payment belongs to another organization', 403)
    if not 0 < minutes <= 2_147_483_647 or not reference or len(reference) > 100:
        raise PaymentReceiptError('Payment has no valid purchased entitlement')
    plan = metadata.get('plan_code') or None
    if plan is not None and (not isinstance(plan, str) or len(plan) > 50):
        raise PaymentReceiptError('Payment has invalid plan metadata')
    return VerifiedPaymentReceipt(minutes, reference, plan)


async def verify_payment_receipt(*, gateway: str, order_id: str, payment_id: str,
                                 organization_id: int, credentials: dict) -> VerifiedPaymentReceipt:
    """Fetch a paid provider receipt and bind its frozen metadata to this tenant."""
    if gateway not in {'razorpay', 'stripe'}:
        raise PaymentReceiptError('Unsupported payment gateway')
    if not order_id or not payment_id:
        raise PaymentReceiptError('Payment identifiers are required')
    if gateway == 'razorpay':
        key = credentials.get('razorpay_key_id')
        secret = credentials.get('razorpay_key_secret')
        if not key or not secret:
            raise PaymentReceiptError('Razorpay gateway is not configured')
    elif not credentials.get('stripe_secret_key'):
        raise PaymentReceiptError('Stripe gateway is not configured')

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if gateway == 'razorpay':
                payment_response = await client.get(
                    'https://api.razorpay.com/v1/payments/' + quote(payment_id, safe=''), auth=(key, secret))
                payment_response.raise_for_status()
                order_response = await client.get(
                    'https://api.razorpay.com/v1/orders/' + quote(order_id, safe=''), auth=(key, secret))
                order_response.raise_for_status()
                payment, order = payment_response.json(), order_response.json()
                if (payment.get('id') != payment_id or order.get('id') != order_id
                        or payment.get('order_id') != order_id or payment.get('status') != 'captured'
                        or order.get('status') != 'paid'
                        or not isinstance(order.get('amount'), int) or order['amount'] <= 0
                        or payment.get('amount') != order['amount']
                        or not order.get('currency') or payment.get('currency') != order['currency']):
                    raise PaymentReceiptError('Payment is not a matching captured order')
                return _entitlement(order.get('notes') or {}, organization_id, payment_id)

            response = await client.get(
                'https://api.stripe.com/v1/checkout/sessions/' + quote(order_id, safe=''),
                headers={'Authorization': 'Bearer ' + credentials['stripe_secret_key']})
            response.raise_for_status()
            checkout = response.json()
            reference = checkout.get('payment_intent')
            if isinstance(reference, dict):
                reference = reference.get('id')
            if (checkout.get('id') != order_id or checkout.get('mode') != 'payment'
                    or checkout.get('status') != 'complete' or checkout.get('payment_status') != 'paid'
                    or not isinstance(checkout.get('amount_total'), int) or checkout['amount_total'] <= 0
                    or not checkout.get('currency') or not isinstance(reference, str)
                    or payment_id not in {order_id, reference}):
                raise PaymentReceiptError('Checkout has not completed a matching paid payment')
            return _entitlement(checkout.get('metadata') or {}, organization_id, reference)
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        raise PaymentReceiptError('Payment provider could not verify this receipt', 502) from exc
