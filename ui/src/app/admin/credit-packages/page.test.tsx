import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ getCreditPackages: vi.fn(), createCreditPackage: vi.fn() }));
vi.mock("@/lib/kodewavesApi", () => ({ adminApi: mocks }));

import AdminCreditPackagesPage from "./page";

describe("owner credit bundle configuration", () => {
  beforeEach(() => {
    mocks.getCreditPackages.mockReset().mockResolvedValue([]);
    mocks.createCreditPackage.mockReset().mockResolvedValue({});
  });

  it("keeps a new bundle hidden until a positive price is configured", async () => {
    render(<AdminCreditPackagesPage />);
    await screen.findByText(/No top-up bundles created yet/);
    fireEvent.click(screen.getByRole("button", { name: "Create Bundle" }));

    expect(screen.getByRole("switch", { name: "Visible in Billing Store" }).getAttribute("data-state")).toBe("unchecked");
    expect(screen.getByLabelText("Price (INR)")).toHaveProperty("value", "0.00");

    fireEvent.click(screen.getByRole("switch", { name: "Visible in Billing Store" }));
    expect(screen.getByRole("alert").textContent).toMatch(/positive price/);
    expect(screen.getByRole("button", { name: "Save Bundle" })).toHaveProperty("disabled", true);

    fireEvent.change(screen.getByLabelText("Price (INR)"), { target: { value: "2.50" } });
    expect(screen.getByRole("button", { name: "Save Bundle" })).toHaveProperty("disabled", false);
  });

  it("lets the owner explicitly confirm a free bundle", async () => {
    render(<AdminCreditPackagesPage />);
    await screen.findByText(/No top-up bundles created yet/);
    fireEvent.click(screen.getByRole("button", { name: "Create Bundle" }));
    fireEvent.click(screen.getByRole("switch", { name: "Visible in Billing Store" }));
    expect(screen.getByRole("button", { name: "Save Bundle" })).toHaveProperty("disabled", true);

    fireEvent.click(screen.getByRole("button", { name: "Confirm this as a free bundle" }));
    expect(screen.getByRole("button", { name: "Save Bundle" })).toHaveProperty("disabled", false);
    fireEvent.click(screen.getByRole("button", { name: "Save Bundle" }));

    await waitFor(() => expect(mocks.createCreditPackage).toHaveBeenCalledWith(expect.objectContaining({
      price_cents: 0, is_active: true,
    })));
  });
});
