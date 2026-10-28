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
    fireEvent.click(screen.getByRole("switch", { name: "Show in public pricing and self-service checkout" }));
    fireEvent.click(screen.getByRole("switch", { name: "Default fallback plan" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Plan" }));
    await waitFor(() => expect(mocks.createPlan).toHaveBeenCalledWith(expect.objectContaining({
      included_minutes: 0, max_agents: 0, max_concurrent_calls: 0,
      has_crm_access: false, has_widget_access: false, is_default: true,
      is_public: false,
    })));
  });
});
