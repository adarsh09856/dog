import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  valid: null as boolean | null,
  message: "Unable to reach license service",
  refresh: vi.fn(),
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/workflow" }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ isAuthenticated: true }) }));
vi.mock("@/context/ClientEntitlementsContext", () => ({ useClientEntitlements: () => ({
  isClientEdition: true, loading: false, valid: state.valid, message: state.message,
  hasFeature: () => false, refresh: state.refresh,
}) }));
vi.mock("@/context/AppConfigContext", () => ({ useAppConfig: () => ({ config: null }) }));
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

describe("client installation access", () => {
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
