import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getPublicPlans: vi.fn(),
  getPublicCreditPackages: vi.fn(),
}));

vi.mock("@/lib/kodewavesApi", () => ({
  publicApi: {
    getPublicPlans: mocks.getPublicPlans,
    getPublicCreditPackages: mocks.getPublicCreditPackages,
  },
}));

import PricingPage from "./page";

describe("public pricing", () => {
  beforeEach(() => {
    mocks.getPublicPlans.mockReset();
    mocks.getPublicCreditPackages.mockReset();
  });

  it("does not display hard-coded prices after a live pricing request fails and can retry", async () => {
    mocks.getPublicPlans
      .mockRejectedValueOnce(new Error("plans unavailable"))
      .mockResolvedValueOnce([{
        id: "starter",
        name: "Starter",
        code: "starter",
        monthly_price_inr: 2499,
        monthly_price_usd: 30,
        included_minutes: 500,
        overage_rate_per_minute: 1.2,
        max_concurrent_calls: 2,
        allow_user_byok: true,
        features: ["WebRTC Web Widget"],
        is_active: true,
      }]);
    mocks.getPublicCreditPackages
      .mockRejectedValueOnce(new Error("packages unavailable"))
      .mockResolvedValueOnce([]);

    render(<PricingPage />);

    expect(await screen.findByText(/Plans could not be loaded/)).toBeTruthy();
    expect(screen.queryByText("₹1,499")).toBeNull();
    expect(screen.queryByText("99.99% Guaranteed SLA")).toBeNull();

    fireEvent.click(screen.getAllByRole("button", { name: "Retry" })[0]);

    await waitFor(() => expect(screen.getByText("Starter")).toBeTruthy());
    expect(screen.getByText("₹2,499")).toBeTruthy();
    expect(mocks.getPublicPlans).toHaveBeenCalledTimes(2);
    expect(mocks.getPublicCreditPackages).toHaveBeenCalledTimes(2);
  });
});
