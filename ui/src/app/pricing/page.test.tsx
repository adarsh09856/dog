import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getPublicPlans: vi.fn(),
  getPublicCreditOffers: vi.fn(),
}));

vi.mock("@/lib/kodewavesApi", () => ({
  publicApi: {
    getPublicPlans: mocks.getPublicPlans,
    getPublicCreditOffers: mocks.getPublicCreditOffers,
  },
}));

vi.mock("@/components/PublicSiteChrome", () => ({ PublicHeader: () => null, PublicFooter: () => null }));

import PricingPage from "./page";

describe("public pricing", () => {
  beforeEach(() => {
    mocks.getPublicPlans.mockReset();
    mocks.getPublicCreditOffers.mockReset();
  });

  it("does not display hard-coded prices after a live pricing request fails and can retry", async () => {
    mocks.getPublicPlans
      .mockRejectedValueOnce(new Error("plans unavailable"))
      .mockResolvedValueOnce([{
        id: "starter",
        name: "Starter",
        code: "starter",
        monthly_price_cents: 249900,
        annual_price_cents: 2499000,
        currency: "INR",
        monthly_price_inr: 2499,
        monthly_price_usd: null,
        included_minutes: 500,
        max_agents: 5,
        max_concurrent_calls: 2,
        allow_user_byok: true,
        features: ["WebRTC Web Widget"],
        is_active: true,
      }]);
    mocks.getPublicCreditOffers
      .mockRejectedValueOnce(new Error("packages unavailable"))
      .mockResolvedValueOnce([]);

    render(<PricingPage />);

    expect(await screen.findByText(/Plans could not be loaded/)).toBeTruthy();
    expect(screen.queryByText("₹1,499")).toBeNull();
    expect(screen.queryByText("99.99% Guaranteed SLA")).toBeNull();
    expect(screen.queryByText(/Your Monthly Savings/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "What is included in the displayed price?" }));
    expect(screen.getByText(/one-time payment for 30 days of plan access/)).toBeTruthy();
    expect(screen.getByText(/A free plan grants its configured trial minutes once when activated; paid plans credit configured minutes once per payment/)).toBeTruthy();

    fireEvent.click(screen.getAllByRole("button", { name: "Retry" })[0]);

    await waitFor(() => expect(screen.getByText("Starter")).toBeTruthy());
    expect(screen.getByText("₹2,499")).toBeTruthy();
    expect(screen.getByText("5 agents")).toBeTruthy();
    expect(screen.queryByText("Save 20%")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Annual" }));
    expect(screen.getByText("₹24,990")).toBeTruthy();
    expect(mocks.getPublicPlans).toHaveBeenCalledTimes(2);
    expect(mocks.getPublicCreditOffers).toHaveBeenCalledTimes(2);
  });

  it("shows configured plans while the credit catalog is still pending", async () => {
    mocks.getPublicPlans.mockResolvedValue([{
      id: "starter",
      name: "Starter",
      code: "starter",
      monthly_price_cents: 2999,
      annual_price_cents: 0,
      currency: "USD",
      included_minutes: 100,
      max_agents: 3,
      max_concurrent_calls: 1,
      features: [],
      is_active: true,
    }]);
    mocks.getPublicCreditOffers.mockReturnValue(new Promise(() => {}));

    render(<PricingPage />);

    expect(await screen.findByText("Starter")).toBeTruthy();
    expect(screen.getByText("$29.99")).toBeTruthy();
    expect(screen.getByText(/Loading credit bundles/)).toBeTruthy();
  });

  it("formats configured foreign-currency prices with international grouping", async () => {
    mocks.getPublicPlans.mockResolvedValue([{
      id: "enterprise",
      name: "Enterprise",
      code: "enterprise",
      monthly_price_cents: 12345678,
      annual_price_cents: 0,
      currency: "USD",
      included_minutes: 100,
      max_agents: 10,
      max_concurrent_calls: 5,
      features: [],
      is_active: true,
    }]);
    mocks.getPublicCreditOffers.mockResolvedValue([{
      id: "bundle-large",
      name: "Large bundle",
      minutes: 5000,
      bonus_minutes: 0,
      price_cents: 12345678,
      currency: "USD",
      is_popular: false,
    }]);

    render(<PricingPage />);

    expect(await screen.findAllByText("$123,456.78")).toHaveLength(2);
    expect(screen.queryByText("$1,23,456.78")).toBeNull();
  });

  it("shows a configured free credit package as redeemable", async () => {
    mocks.getPublicPlans.mockResolvedValue([]);
    mocks.getPublicCreditOffers.mockResolvedValue([{
      id: "welcome-20", name: "Welcome minutes", minutes: 20,
      bonus_minutes: 0, price_cents: 0, currency: "INR", is_popular: false,
    }]);

    render(<PricingPage />);

    expect(await screen.findByText("Welcome minutes")).toBeTruthy();
    expect(screen.getByText("Free")).toBeTruthy();
    expect(screen.getByText(/One-time redemption per organization/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Redeem free minutes/ }).getAttribute("href"))
      .toBe("/auth/login?credit_package=welcome-20");
  });

  it("shows an annual-only offer as annual and preserves that cycle into sign-in", async () => {
    mocks.getPublicPlans.mockResolvedValue([{
      id: "annual",
      name: "Annual Plan",
      code: "annual_plan",
      monthly_price_cents: 0,
      annual_price_cents: 120000,
      currency: "INR",
      included_minutes: 100,
      max_agents: 3,
      max_concurrent_calls: 1,
      features: [],
      is_active: true,
    }]);
    mocks.getPublicCreditOffers.mockResolvedValue([]);

    render(<PricingPage />);

    expect(await screen.findByText("₹1,200")).toBeTruthy();
    expect(screen.getByText(/365 days of access/)).toBeTruthy();
    const reviewLink = screen.getByRole("link", { name: /Review in your account/ });
    expect(reviewLink.getAttribute("href")).toBe("/auth/login?plan=annual_plan&billing_cycle=annual");
  });

  it("labels free-plan minutes as a one-time activation grant rather than a payment credit", async () => {
    mocks.getPublicPlans.mockResolvedValue([{
      id: "free",
      name: "Community",
      code: "community",
      monthly_price_cents: 0,
      annual_price_cents: 0,
      currency: "INR",
      included_minutes: 60,
      max_agents: 1,
      max_concurrent_calls: 1,
      features: [],
      is_active: true,
    }]);
    mocks.getPublicCreditOffers.mockResolvedValue([]);

    render(<PricingPage />);

    expect(await screen.findByText("Community")).toBeTruthy();
    expect(screen.getByText(/60 one-time trial minutes on activation/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Do credits or included minutes expire?" }));
    expect(screen.getByText(/Free-plan trial minutes are granted once at activation/)).toBeTruthy();
  });

  it("does not label a paid offer with a missing price as free", async () => {
    mocks.getPublicPlans.mockResolvedValue([{
      id: "annual",
      name: "Annual Plan",
      code: "annual_plan",
      monthly_price_cents: 0,
      annual_price_cents: 120000,
      currency: "",
      included_minutes: 100,
      max_agents: 3,
      max_concurrent_calls: 1,
      features: [],
      is_active: true,
    }]);
    mocks.getPublicCreditOffers.mockResolvedValue([]);

    render(<PricingPage />);

    expect(await screen.findByText("Price unavailable")).toBeTruthy();
    expect(screen.queryByText("Free")).toBeNull();
  });

  it.each([undefined, null, -1, 1.5])("hides malformed plan prices (%s)", async (price) => {
    mocks.getPublicPlans.mockResolvedValue([{
      id: "incomplete", name: "Incomplete plan", code: "incomplete",
      monthly_price_cents: price, annual_price_cents: 0, currency: "INR",
      included_minutes: null, max_agents: 3, max_concurrent_calls: 1,
      features: [], is_active: true,
    }]);
    mocks.getPublicCreditOffers.mockResolvedValue([]);
    render(<PricingPage />);
    expect(await screen.findByText("Price unavailable")).toBeTruthy();
    expect(screen.queryByText("Free")).toBeNull();
    expect(screen.queryByText("No payment required for this plan")).toBeNull();
    expect(screen.getByText(/— included minutes/)).toBeTruthy();
  });

  it("does not offer an invalid credit bundle for purchase", async () => {
    mocks.getPublicPlans.mockResolvedValue([]);
    mocks.getPublicCreditOffers.mockResolvedValue([{
      id: "broken", name: "Broken bundle", minutes: null,
      bonus_minutes: 0, price_cents: -1, currency: "INR",
    }]);
    render(<PricingPage />);
    expect(await screen.findByText("Bundle details unavailable")).toBeTruthy();
    expect(screen.getByText("Price unavailable")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Continue to wallet/ })).toBeNull();
  });

  it("keeps the selected credit bundle through the sign-in link", async () => {
    mocks.getPublicPlans.mockResolvedValue([]);
    mocks.getPublicCreditOffers.mockResolvedValue([{
      id: "bundle-500", name: "500 minute bundle", minutes: 500,
      bonus_minutes: 25, price_cents: 150000, currency: "INR", is_popular: true,
    }, {
      id: "bundle-100", name: "100 minute bundle", minutes: 100,
      bonus_minutes: 10, price_cents: 30000, currency: "INR", is_popular: false,
    }]);

    render(<PricingPage />);

    const [link] = await screen.findAllByRole("link", { name: /Continue to wallet/ });
    expect(link.getAttribute("href")).toBe("/auth/login?credit_package=bundle-500");
    expect(screen.getAllByText("Popular")).toHaveLength(1);
    expect(screen.getAllByText("One-time payment. Wallet minutes do not expire.")).toHaveLength(2);
  });
});
