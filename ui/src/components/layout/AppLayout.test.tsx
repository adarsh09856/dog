import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  valid: null as boolean | null,
  message: "Unable to reach license service",
  refresh: vi.fn(),
  pathname: "/workflow",
  isAuthenticated: true,
  backendConfig: null as null | { backendStatus: string; backendUrl?: string; backendMessage?: string },
}));
vi.mock("next/navigation", () => ({ usePathname: () => state.pathname }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ isAuthenticated: state.isAuthenticated }) }));
vi.mock("@/context/ClientEntitlementsContext", () => ({ useClientEntitlements: () => ({
  isClientEdition: true, loading: false, valid: state.valid, message: state.message,
  hasFeature: () => false, refresh: state.refresh,
}) }));
vi.mock("@/context/AppConfigContext", () => ({ useAppConfig: () => ({ config: state.backendConfig, loading: false, refresh: state.refresh }) }));
vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: () => ({ tagline: "Calls answered in your brand voice" }),
}));
vi.mock("@/context/LeadFormsContext", () => ({ LeadFormsProvider: ({ children }: { children: ReactNode }) => children }));
vi.mock("@/components/ui/sidebar", () => ({
  SidebarProvider: ({ children }: { children: ReactNode }) => children,
  SidebarInset: ({ children }: { children: ReactNode }) => children,
  useSidebar: () => ({ toggleSidebar: vi.fn() }),
}));
vi.mock("./AppSidebar", () => ({ AppSidebar: () => null }));
vi.mock("@/components/BrandLogo", () => ({ BrandLogo: () => null }));

import AppLayout from "./AppLayout";

afterEach(() => { cleanup(); state.refresh.mockReset(); });

describe.each(["/platform", "/deployment"])('%s public page chrome', (pathname) => {
  it.each([true, false])("does not render workspace chrome or backend warnings for auth=%s", (isAuthenticated) => {
    state.pathname = pathname;
    state.isAuthenticated = isAuthenticated;
    state.backendConfig = { backendStatus: "unreachable", backendUrl: "api.example", backendMessage: "not available" };
    render(<AppLayout><p>public marketing content</p></AppLayout>);
    expect(screen.getByText("public marketing content")).toBeTruthy();
    expect(screen.queryByText("Workspace")).toBeNull();
    expect(screen.queryByText("Calls answered in your brand voice")).toBeNull();
    expect(screen.queryByText("Backend connection failed")).toBeNull();
  });
});

describe("client installation access", () => {
  beforeEach(() => {
    state.pathname = "/workflow";
    state.isAuthenticated = true;
    state.backendConfig = null;
  });
  it("renders the authenticated workspace header", () => {
    state.valid = true;
    render(<AppLayout><p>protected content</p></AppLayout>);
    expect(screen.getByText("Voice agents")).toBeTruthy();
  });

  it("shows verification failure and retries rather than claiming the feature is excluded", () => {
    state.valid = null;
    render(<AppLayout><p>protected content</p></AppLayout>);
    expect(screen.getByText("Installation access unavailable")).toBeTruthy();
    expect(screen.getByText(/Unable to reach license service/)).toBeTruthy();
    expect(screen.queryByText(/does not include/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(state.refresh).toHaveBeenCalledOnce();
  });

  it("explains a feature exclusion only after a valid license is verified", () => {
    state.valid = true;
    render(<AppLayout><p>protected content</p></AppLayout>);
    expect(screen.getByText("Feature unavailable")).toBeTruthy();
    expect(screen.getByText(/does not include the voice feature/)).toBeTruthy();
  });
});
