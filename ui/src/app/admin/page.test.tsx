import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ getStats: vi.fn() }));

vi.mock("@/lib/kodewavesApi", () => ({
  adminApi: { getStats: mocks.getStats },
}));

import AdminDashboardPage from "./page";

describe("owner dashboard database status", () => {
  beforeEach(() => {
    mocks.getStats.mockReset();
  });

  afterEach(() => vi.restoreAllMocks());

  it("reports connected only after live telemetry loads", async () => {
    mocks.getStats.mockResolvedValue({
      total_calls: 0,
      active_calls: 0,
      completed_calls: 0,
      total_minutes: 0,
      total_revenue_inr: null,
      gross_margin_percent: null,
      system_health: "healthy",
    });

    const view = render(<AdminDashboardPage />);

    expect(await screen.findByText("Database connected")).toBeTruthy();
    view.unmount();
  });

  it("does not claim a live database connection when telemetry fails", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    mocks.getStats.mockRejectedValue(new Error("database unavailable"));

    const view = render(<AdminDashboardPage />);

    expect(await screen.findByText("Database unavailable")).toBeTruthy();
    expect(screen.getByText("Telemetry Error: database unavailable")).toBeTruthy();
    view.unmount();
  });
});
