import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  billingFeature: true,
  isClientEdition: true,
  companyName: "Acme Voice",
  user: { id: 9, email: "client-admin@example.test", is_superuser: true, organizationId: 1 },
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: mocks.user, loading: false }) }));
vi.mock("@/context/ClientEntitlementsContext", () => ({
  useClientEntitlements: () => ({
    hasFeature: (feature: string) => feature !== "billing" || mocks.billingFeature,
    isClientEdition: mocks.isClientEdition,
  }),
}));
vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: () => ({ company_name: mocks.companyName }),
}));
vi.mock("@/components/CallEventsSection", () => ({ CallEventsSection: () => null }));
vi.mock("@/components/ClientBrandingSettingsCard", () => ({ ClientBrandingSettingsCard: () => <div>Business branding controls</div> }));
vi.mock("@/components/ClientUsersSettingsCard", () => ({ ClientUsersSettingsCard: () => <div>Workspace user controls</div> }));
vi.mock("@/components/ClientWorkspacesSettingsCard", () => ({ ClientWorkspacesSettingsCard: () => <div>Workspace settings controls</div> }));
vi.mock("@/components/MCPSection", () => ({ MCPSection: () => null }));
vi.mock("@/components/OrganizationPreferencesSection", () => ({ OrganizationPreferencesSection: () => null }));
vi.mock("@/components/TelemetrySection", () => ({ TelemetrySection: () => null }));

import SettingsPage from "./page";

describe("workspace settings role boundaries", () => {
  beforeEach(() => {
    mocks.billingFeature = true;
    mocks.isClientEdition = true;
    mocks.companyName = "Acme Voice";
    mocks.user = { id: 9, email: "client-admin@example.test", is_superuser: true, organizationId: 1 };
  });

  it("shows client business administration without installation or owner controls", () => {
    render(<SettingsPage />);

    expect(screen.getByRole("heading", { name: "Workspace administration" })).toBeTruthy();
    expect(screen.getByText("Business branding controls")).toBeTruthy();
    expect(screen.getByText("Workspace user controls")).toBeTruthy();
    expect(screen.getByText("Workspace settings controls")).toBeTruthy();
    expect(screen.queryByText(/Client installation administration|Client Installation License/i)).toBeNull();
    expect(screen.queryByText(/Request a domain or server IP change/i)).toBeNull();
    expect(screen.queryByRole("link", { name: /Platform Owner Console/i })).toBeNull();
  });

  it("keeps the platform owner console separate in the hosted edition", () => {
    mocks.isClientEdition = false;
    render(<SettingsPage />);

    expect(screen.getByText("Acme Voice platform owner")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open Platform Owner Console/i })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Workspace administration" })).toBeNull();
  });

  it("shows the licensed usage wallet only when the client plan includes billing", () => {
    mocks.billingFeature = false;
    const { rerender } = render(<SettingsPage />);
    expect(screen.queryByRole("link", { name: /Open licensed usage wallet/i })).toBeNull();

    mocks.billingFeature = true;
    rerender(<SettingsPage />);
    expect(screen.getByRole("link", { name: /Open licensed usage wallet/i })).toBeTruthy();
    expect(screen.queryByText(/upgrade subscription plans/i)).toBeNull();
  });
});
