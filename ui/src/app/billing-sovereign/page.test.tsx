import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  user: { id: 7 },
  getWallet: vi.fn(),
  getLedger: vi.fn(),
  getPlans: vi.fn(),
  getPublicCreditOffers: vi.fn(),
  createOrder: vi.fn(),
  getConfig: vi.fn(),
  verifyPayment: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ user: mocks.user, loading: false }),
}));
vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: () => ({ company_name: "Customer Brand" }),
}));
vi.mock("@/lib/kodewavesApi", () => ({
  sovereignBillingApi: {
    getWallet: mocks.getWallet,
    getLedger: mocks.getLedger,
    getPlans: mocks.getPlans,
  },
  publicApi: { getPublicCreditOffers: mocks.getPublicCreditOffers },
  paymentsApi: {
    createOrder: mocks.createOrder,
    getConfig: mocks.getConfig,
    verifyPayment: mocks.verifyPayment,
  },
}));

import SovereignBillingPage from "./page";

describe("manual plan renewal", () => {
  beforeEach(() => {
    mocks.getPublicCreditOffers.mockResolvedValue([]);
    mocks.getConfig.mockResolvedValue({ razorpay_enabled: false, stripe_enabled: false, default_currency: "INR" });
    mocks.verifyPayment.mockResolvedValue({ message: "Payment verified" });
  });

  afterEach(() => {
    window.history.replaceState({}, "", "/");
    Reflect.deleteProperty(window, "Razorpay");
    vi.restoreAllMocks();
  });

  it("allows renewing the current paid plan and explains plan replacement before payment", async () => {
    mocks.getWallet.mockResolvedValue({
      plan_code: "pro",
      plan_name: "Renamed Pro Display Name",
      included_minutes: 100,
      credit_balance_minutes: 100,
      bonus_minutes: 0,
      total_available_minutes: 100,
      is_frozen: false,
      plan_expires_at: "2030-01-01T00:00:00+00:00",
    });
    mocks.getLedger.mockResolvedValue([]);
    mocks.getPlans.mockResolvedValue([
      { id: "1", name: "Pro", code: "pro", currency: "USD", monthly_price_cents: 2999,
        annual_price_cents: 29900, included_minutes: 100, max_concurrent_calls: 2 },
      { id: "2", name: "Team", code: "team", currency: "USD", monthly_price_cents: 5999,
        annual_price_cents: 0, included_minutes: 200, max_concurrent_calls: 4 },
    ]);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<SovereignBillingPage />);

    const renew = await screen.findByRole("button", { name: "Renew Plan" });
    expect((renew as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(renew);
    expect(confirm).toHaveBeenLastCalledWith(expect.stringContaining("after your current expiry"));
    fireEvent.click(screen.getByRole("button", { name: "Choose Plan" }));
    expect(confirm).toHaveBeenLastCalledWith(expect.stringContaining("Unused time on a different plan is not carried over"));
    expect(mocks.createOrder).not.toHaveBeenCalled();
  });

  it("applies the selected plan and annual cycle passed from public pricing", async () => {
    mocks.getWallet.mockResolvedValue({
      plan_code: "starter",
      plan_name: "Starter",
      included_minutes: 100,
      credit_balance_minutes: 100,
      bonus_minutes: 0,
      total_available_minutes: 100,
      is_frozen: false,
    });
    mocks.getLedger.mockResolvedValue([]);
    mocks.getPlans.mockResolvedValue([
      { id: "1", name: "Pro", code: "pro", currency: "USD", monthly_price_cents: 2999,
        annual_price_cents: 29900, included_minutes: 100, max_concurrent_calls: 2 },
    ]);
    window.history.replaceState({}, "", "/billing-sovereign?plan=pro&billing_cycle=annual");
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<SovereignBillingPage />);

    expect(await screen.findByText("$299.00")).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Choose Plan" }));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("365 days"));
  });

  it("carries a public credit bundle into the wallet and requires confirmation before checkout", async () => {
    mocks.getWallet.mockResolvedValue({
      plan_code: "starter", plan_name: "Starter", included_minutes: 100,
      credit_balance_minutes: 100, bonus_minutes: 0, total_available_minutes: 100,
      is_frozen: false,
    });
    mocks.getLedger.mockResolvedValue([]);
    mocks.getPlans.mockResolvedValue([]);
    mocks.getPublicCreditOffers.mockResolvedValue([{
      id: "bundle-500", name: "500 minute bundle", minutes: 500,
      bonus_minutes: 25, price_cents: 150000, currency: "INR", is_popular: true,
    }]);
    window.history.replaceState({}, "", "/billing-sovereign?credit_package=bundle-500");
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<SovereignBillingPage />);

    expect(await screen.findByText("500 minute bundle")).toBeTruthy();
    expect(screen.getByText("Popular")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toMatch(/selected a bundle from public pricing/i);
    fireEvent.click(screen.getByRole("button", { name: "Continue to payment" }));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("525 wallet minutes"));
    expect(mocks.getConfig).not.toHaveBeenCalled();
    expect(mocks.createOrder).not.toHaveBeenCalled();
  });

  it("creates and verifies a Razorpay order for the exact selected credit package", async () => {
    mocks.getWallet.mockResolvedValue({
      plan_code: "starter", plan_name: "Starter", included_minutes: 100,
      credit_balance_minutes: 100, bonus_minutes: 0, total_available_minutes: 100,
      is_frozen: false,
    });
    mocks.getLedger.mockResolvedValue([]);
    mocks.getPlans.mockResolvedValue([]);
    mocks.getPublicCreditOffers.mockResolvedValue([{
      id: "bundle-500", name: "500 minute bundle", minutes: 500,
      bonus_minutes: 25, price_cents: 150000, currency: "INR",
    }]);
    mocks.getConfig.mockResolvedValue({
      razorpay_enabled: true, razorpay_key_id: "rzp_test_key",
      stripe_enabled: false, default_currency: "INR",
    });
    mocks.createOrder.mockResolvedValue({
      order_id: "order-123", amount: 150000, currency: "INR", gateway: "razorpay",
    });
    mocks.verifyPayment.mockResolvedValue({ message: "500 minutes credited" });
    window.history.replaceState({}, "", "/billing-sovereign?credit_package=bundle-500");
    vi.spyOn(window, "confirm").mockReturnValue(true);
    let checkoutHandler: ((result: {
      razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string;
    }) => Promise<void>) | undefined;
    class RazorpayStub {
      constructor(options: { handler: NonNullable<typeof checkoutHandler> }) {
        checkoutHandler = options.handler;
      }
      open() { return undefined; }
    }
    Object.defineProperty(window, "Razorpay", { configurable: true, value: RazorpayStub });

    render(<SovereignBillingPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Continue to payment" }));
    await screen.findByText("500 minute bundle");
    await waitFor(() => expect(mocks.createOrder).toHaveBeenCalledWith({
      package_id: "bundle-500", gateway: "razorpay",
    }));
    expect(checkoutHandler).toBeDefined();
    vi.spyOn(window, "alert").mockImplementation(() => undefined);
    await act(async () => {
      await checkoutHandler!({
        razorpay_order_id: "order-123", razorpay_payment_id: "payment-456",
        razorpay_signature: "signed-callback",
      });
    });
    expect(mocks.verifyPayment).toHaveBeenCalledWith({
      gateway: "razorpay", order_id: "order-123", payment_id: "payment-456",
      signature: "signed-callback", package_id: "bundle-500",
    });
  });
});
