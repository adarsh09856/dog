import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  authLoading: false,
  user: { id: 9, email: "client-admin@example.test", is_superuser: true, organizationId: 1 },
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: mocks.user, loading: mocks.authLoading }) }));
vi.mock("@/context/ClientEntitlementsContext", () => ({
  useClientEntitlements: () => ({ hasFeature: () => true, isClientEdition: true }),
}));
vi.mock("@/lib/kodewavesApi", () => ({ apiFetch: mocks.apiFetch }));
vi.mock("@/components/CallEventsSection", () => ({ CallEventsSection: () => null }));
vi.mock("@/components/ClientBrandingSettingsCard", () => ({ ClientBrandingSettingsCard: () => null }));
vi.mock("@/components/ClientUsersSettingsCard", () => ({ ClientUsersSettingsCard: () => null }));
vi.mock("@/components/ClientWorkspacesSettingsCard", () => ({ ClientWorkspacesSettingsCard: () => null }));
vi.mock("@/components/MCPSection", () => ({ MCPSection: () => null }));
vi.mock("@/components/OrganizationPreferencesSection", () => ({ OrganizationPreferencesSection: () => null }));
vi.mock("@/components/TelemetrySection", () => ({ TelemetrySection: () => null }));

import SettingsPage from "./page";

describe("client installation binding change requests", () => {
  beforeEach(() => {
    mocks.authLoading = false;
    mocks.apiFetch.mockReset();
    mocks.apiFetch.mockImplementation((endpoint: string) => {
      if (endpoint === "/installation/license") {
        return Promise.resolve({
          edition: "client",
          valid: false,
          binding_request_available: true,
          installation_id: "client-9",
          domains: ["old.customer.example"],
          ip_ranges: ["203.0.113.7/32"],
          message: "The configured public domain is not in this installation license.",
        });
      }
      return Promise.resolve({
        request_id: 31,
        submitted_at: "2026-10-29T10:00:00Z",
        message: "Your binding change request was sent to Kodewaves for owner review.",
      });
    });
  });

  it("waits for authentication before loading installation status", async () => {
    mocks.authLoading = true;
    const { rerender } = render(<SettingsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(mocks.apiFetch).not.toHaveBeenCalled();
    mocks.authLoading = false;
    rerender(<SettingsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(mocks.apiFetch).toHaveBeenCalledWith("/installation/license");
  });

  it("lets a client admin request a binding update even when the configured domain is stale", async () => {
    render(<SettingsPage />);
    await act(async () => { await Promise.resolve(); });

    expect(screen.getByText("The configured public domain is not in this installation license.")).toBeTruthy();
    expect(screen.getByDisplayValue("old.customer.example")).toBeTruthy();
    expect(screen.getByDisplayValue("203.0.113.7/32")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Requested public domains"), {
      target: { value: "voice.new-customer.example" },
    });
    fireEvent.change(screen.getByLabelText("Requested source IPs/CIDRs (optional)"), {
      target: { value: "198.51.100.10/32" },
    });
    fireEvent.change(screen.getByLabelText("Reason for the change"), {
      target: { value: "Moving to a new server" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Request owner review" }));
    });

    expect(mocks.apiFetch).toHaveBeenCalledWith("/installation/binding-requests", {
      method: "POST",
      body: JSON.stringify({
        domains: ["voice.new-customer.example"],
        ip_ranges: ["198.51.100.10/32"],
        reason: "Moving to a new server",
      }),
    });
    expect(screen.getByRole("status").textContent).toContain("Request #31");
  });
});
