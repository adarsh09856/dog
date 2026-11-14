import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  isClientEdition: false,
  hasFeature: vi.fn(() => true),
  user: { is_superuser: false },
}));

vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: () => ({ company_name: "Acme Voice" }),
}));
vi.mock("@/context/ClientEntitlementsContext", () => ({
  useClientEntitlements: () => ({
    isClientEdition: mocks.isClientEdition,
    hasFeature: mocks.hasFeature,
  }),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: mocks.user }) }));

import WorkspaceAdminPage from "./page";

describe("workspace admin landing page", () => {
  beforeEach(() => {
    mocks.isClientEdition = false;
    mocks.hasFeature.mockReset().mockReturnValue(true);
    mocks.user = { is_superuser: false };
  });

  afterEach(() => vi.unstubAllEnvs());

  it("shows workspace operations and routes without platform-owner telemetry", () => {
    render(<WorkspaceAdminPage />);

    expect(screen.getByRole("heading", { name: "Workspace admin" })).toBeTruthy();
    expect(screen.getAllByRole("link").some((link) => link.getAttribute("href") === "/crm")).toBe(true);
    expect(screen.getAllByRole("link").some((link) => link.getAttribute("href") === "/workflow")).toBe(true);
    expect(screen.getAllByRole("link").some((link) => link.getAttribute("href") === "/settings")).toBe(true);
    expect(screen.queryByText("Sovereign Control Plane")).toBeNull();
    expect(screen.queryByText("Active Live Calls")).toBeNull();
  });

  it("filters workspace tools by client entitlements", () => {
    mocks.isClientEdition = true;
    mocks.hasFeature.mockImplementation((feature: string) => feature !== "campaigns");

    render(<WorkspaceAdminPage />);

    expect(screen.getAllByRole("link").some((link) => link.getAttribute("href") === "/crm")).toBe(true);
    expect(screen.queryByRole("link", { name: /Campaigns/ })).toBeNull();
    expect(screen.getAllByRole("link").some((link) => link.getAttribute("href") === "/workflow")).toBe(true);
  });
});
