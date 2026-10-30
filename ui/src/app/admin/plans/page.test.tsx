import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ getPlans: vi.fn(), createPlan: vi.fn() }));
vi.mock("@/lib/kodewavesApi", () => ({ adminApi: mocks }));

import AdminPlansPage from "./page";

describe("owner plan configuration", () => {
  beforeEach(() => {
    mocks.getPlans.mockReset().mockResolvedValue([]);
    mocks.createPlan.mockReset().mockResolvedValue({});
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows a failed load and lets the owner retry instead of claiming an empty catalog", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    mocks.getPlans.mockRejectedValueOnce(new Error("Catalog unavailable"));
    render(<AdminPlansPage />);
    expect((await screen.findByRole("alert")).textContent).toContain("Catalog unavailable");
    expect(screen.queryByText(/No plans created yet/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByText(/No plans created yet/);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("saves zero quotas and feature denials with accurate manual-renewal terms", async () => {
    render(<AdminPlansPage />);
    await screen.findByText(/No plans created yet/);
    expect(screen.getByText(/manual renewal/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Create Plan" }));
    fireEvent.change(screen.getByLabelText("Minutes credited per purchase"), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText("Max Voice Agents"), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText("Max Concurrent Voice Calls"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("switch", { name: "CRM access" }));
    fireEvent.click(screen.getByRole("switch", { name: "Widget access" }));
    fireEvent.click(screen.getByRole("switch", { name: "Campaigns access" }));
    fireEvent.click(screen.getByRole("switch", { name: "Show in public pricing and self-service checkout" }));
    fireEvent.click(screen.getByRole("switch", { name: "Default fallback plan" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Plan" }));
    await waitFor(() => expect(mocks.createPlan).toHaveBeenCalledWith(expect.objectContaining({
      included_minutes: 0, max_agents: 0, max_concurrent_calls: 0,
      has_crm_access: false, has_widget_access: false, is_default: true,
      has_campaigns_access: false,
      is_public: false,
    })));
  });

  it("shows plan enforcement, capacity and owner actions together", async () => {
    mocks.getPlans.mockResolvedValue([{
      id: "pro-id", name: "Growth Pro", code: "growth-pro", currency: "INR",
      monthly_price_cents: 499900, annual_price_cents: 4990000, included_minutes: 2500,
      max_concurrent_calls: 8, max_agents: 12,
      has_crm_access: true, has_appointments_access: false, has_forms_access: true,
      has_widget_access: true, has_campaigns_access: false, allow_user_byok: false,
      is_active: true, is_public: false, is_default: true,
    }]);

    render(<AdminPlansPage />);

    expect(await screen.findByRole("heading", { name: "Plan governance" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Growth Pro" })).toBeTruthy();
    expect(screen.getByText("Monthly · 30 days").parentElement?.textContent).toMatch(/₹4,999/);
    expect(screen.getByText("Annual · 365 days").parentElement?.textContent).toMatch(/₹49,900/);
    expect(screen.queryByText("Overage / minute")).toBeNull();
    expect(screen.getByText("2,500")).toBeTruthy();
    expect(screen.getByText("Platform-managed keys required")).toBeTruthy();
    expect(screen.getByText("Enforced feature access").parentElement?.textContent).toContain("3/5");
    expect(screen.getByText("Default fallback")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Edit Growth Pro" }));
    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(screen.getByDisplayValue("Growth Pro")).toBeTruthy();
  });
});
