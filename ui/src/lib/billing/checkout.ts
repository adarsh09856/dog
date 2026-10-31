import { paymentsApi, type CreateOrderPayload, type VerifyPaymentResult } from "@/lib/kodewavesApi";

type RazorpayResponse = {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
};
type CheckoutOptions = {
  key: string;
  order_id: string;
  amount: number;
  currency: string;
  name: string;
  description?: string;
  handler: (response: RazorpayResponse) => void;
  modal: { ondismiss: () => void };
};
type RazorpayConstructor = new (options: CheckoutOptions) => { open: () => void };
declare global {
  interface Window { Razorpay?: RazorpayConstructor }
}

let scriptLoading: Promise<void> | undefined;
async function loadRazorpay(): Promise<void> {
  if (window.Razorpay) return;
  if (!scriptLoading) {
    scriptLoading = new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://checkout.razorpay.com/v1/checkout.js";
      script.async = true;
      script.onload = () => window.Razorpay ? resolve() : reject(new Error("Checkout could not load."));
      script.onerror = () => { script.remove(); reject(new Error("Checkout could not load. Please retry.")); };
      document.head.appendChild(script);
    }).catch((error) => { scriptLoading = undefined; throw error; });
  }
  await scriptLoading;
}

export type CheckoutResult = { redirected: true } | { redirected: false; receipt: VerifyPaymentResult };

/** Purchase only a configured item; the server owns its price and entitlement. */
export async function startConfiguredCheckout(payload: CreateOrderPayload): Promise<CheckoutResult> {
  const config = await paymentsApi.getConfig();
  const gateway = payload.gateway ?? (config.razorpay_enabled ? "razorpay" : "stripe");
  if (!(gateway === "razorpay" ? config.razorpay_enabled : config.stripe_enabled)) {
    throw new Error("Payments are not configured. Please contact your administrator.");
  }
  if (gateway === "razorpay") await loadRazorpay();
  const order = await paymentsApi.createOrder({ ...payload, gateway });
  if (order.gateway !== gateway) throw new Error("Checkout provider did not match the requested provider.");
  if (gateway === "stripe") {
    const target = new URL(order.checkout_url ?? "");
    if (target.protocol !== "https:") throw new Error("Checkout returned an invalid payment address.");
    window.location.assign(target.href);
    return { redirected: true };
  }
  const razorpayKeyId = order.key_id || config.razorpay_key_id;
  if (!razorpayKeyId || !window.Razorpay) throw new Error("Checkout is unavailable. Please retry.");
  return new Promise((resolve, reject) => {
    let verifying = false;
    const checkout = new window.Razorpay!({
      key: razorpayKeyId, order_id: order.order_id, amount: order.amount,
      currency: order.currency, name: "Kodewaves",
      modal: { ondismiss: () => { if (!verifying) reject(new Error("Checkout was cancelled.")); } },
      handler: (response) => {
        if (verifying) return;
        verifying = true;
        // Use the server-created order ID, never an order ID supplied by the browser callback.
        paymentsApi.verifyPayment({ gateway, order_id: order.order_id,
          payment_id: response.razorpay_payment_id, signature: response.razorpay_signature,
          package_id: payload.package_id, plan_id: payload.plan_id, plan_code: payload.plan_code,
        }).then((receipt) => {
          if (!receipt.success) throw new Error("Payment has not been verified. Refresh your wallet before retrying.");
          resolve({ redirected: false, receipt });
        }).catch(reject);
      },
    });
    checkout.open();
  });
}
