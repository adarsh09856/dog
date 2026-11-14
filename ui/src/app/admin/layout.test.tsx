import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  isClientEdition: false,
  isAuthenticated: true,
  loading: false,
  entitlementsLoading: false,
  user: { is_superuser: false as boolean },
  hasFeature: vi.fn(() => true),
  push: vi.fn(),
  replace: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/admin",
  useRouter: () => ({ push: mocks.push, replace: mocks.replace }),
}));
vi.mock("@/components/BrandLogo", () => ({ BrandLogo: () => <span>Kodewaves</span> }));
vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: () => ({ company_name: "Kodewaves" }),
}));
vi.mock("@/context/ClientEntitlementsContext", () => ({
  useClientEntitlements: () => ({
    isClientEdition: mocks.isClientEdition,
    hasFeature: mocks.hasFeature,
    loading: mocks.entitlementsLoading,
  }),
}));
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: mocks.user,
    isAuthenticated: mocks.isAuthenticated,
    loading: mocks.loading,
    logout: mocks.logout,
  }),
}));

import WorkspaceAdminLayout from "./layout";

describe("workspace admin access boundary", () => {
  beforeEach(() => {
    mocks.isClientEdition = false;
    mocks.isAuthenticated = true;
    mocks.loading = false;
    mocks.entitlementsLoading = false;
    mocks.user = { is_superuser: false };
    mocks.hasFeature.mockReset().mockReturnValue(true);
    mocks.push.mockReset();
    mocks.replace.mockReset();
  });

  afterEach(() => cleanup());

  it("blocks an ordinary hosted account from the workspace admin console", () => {
    render(<WorkspaceAdminLayout><p>Admin content</p></WorkspaceAdminLayout>);

    expect(screen.getByRole("heading", { name: "Administrator access required" })).toBeTruthy();
    expect(screen.queryByText("Admin content")).toBeNull();
    expect(screen.getByText("Ask a platform owner to grant access to workspace controls.")).toBeTruthy();
  });

  it("allows the platform owner into the hosted workspace console", () => {
    mocks.user = { is_superuser: true };
    render(<WorkspaceAdminLayout><p>Admin content</p></WorkspaceAdminLayout>);

    expect(screen.getByText("Admin content")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Superadmin/ })).toBeTruthy();
  });

  it("keeps the licensed client installation administrator in its workspace console", () => {
    mocks.isClientEdition = true;
    mocks.user = { is_superuser: true };
    render(<WorkspaceAdminLayout><p>Client admin content</p></WorkspaceAdminLayout>);

    expect(screen.getByText("Client admin content")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Superadmin/ })).toBeNull();
  });

  it("blocks non-admin users in a licensed client installation", () => {
    mocks.isClientEdition = true;
    render(<WorkspaceAdminLayout><p>Client admin content</p></WorkspaceAdminLayout>);

    expect(screen.getByRole("heading", { name: "Administrator access required" })).toBeTruthy();
    expect(screen.queryByText("Client admin content")).toBeNull();
  });
});
