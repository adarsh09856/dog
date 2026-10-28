import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  auth: {
    user: { id: 1, is_superuser: true },
    loading: false,
    isAuthenticated: true,
    logout: vi.fn(),
  },
  apiFetch: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => mocks.auth }));
vi.mock("@/lib/kodewavesApi", () => ({ apiFetch: mocks.apiFetch }));
vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: () => ({ company_name: "Kodewaves" }),
}));
vi.mock("@/lib/auth/userDisplay", () => ({ getUserEmail: () => "owner@example.com" }));
vi.mock("@/components/BrandLogo", () => ({ BrandLogo: () => <span>logo</span> }));
vi.mock("@/components/ThemeSwitcher", () => ({ default: () => null }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/admin",
  useRouter: () => ({ push: vi.fn() }),
}));

import AdminLayout from "./layout";

describe("admin integrity alert notification", () => {
  beforeEach(() => {
    mocks.auth = {
      user: { id: 1, is_superuser: true },
      loading: false,
      isAuthenticated: true,
      logout: vi.fn(),
    };
    mocks.apiFetch.mockReset().mockResolvedValue([]);
  });

  afterEach(() => vi.clearAllMocks());

  it("shows the unacknowledged integrity count beside Client Installations", async () => {
    mocks.apiFetch.mockResolvedValue([
      { id: 1 },
      { id: 2 },
    ]);

    render(<AdminLayout><div>admin content</div></AdminLayout>);
    await act(async () => { await Promise.resolve(); });

    expect(mocks.apiFetch).toHaveBeenCalledWith("/admin/client-installations/alerts");
    expect(screen.getByLabelText("2 installation integrity alerts")).toBeTruthy();
    expect(screen.getByText("Access & commercial")).toBeTruthy();
    expect(screen.getByText("Operations")).toBeTruthy();
    expect(screen.getByText("Platform owner")).toBeTruthy();
    expect(screen.queryByText("Sovereign Control")).toBeNull();
    expect(screen.getByText("admin content")).toBeTruthy();
  });

  it("does not poll integrity alerts for non-owner accounts", async () => {
    mocks.auth = {
      user: { id: 2, is_superuser: false },
      loading: false,
      isAuthenticated: true,
      logout: vi.fn(),
    };

    render(<AdminLayout><div>blocked content</div></AdminLayout>);
    await act(async () => { await Promise.resolve(); });

    expect(mocks.apiFetch).not.toHaveBeenCalled();
    expect(screen.getByText("Superadmin Access Required")).toBeTruthy();
  });

  it("opens the mobile navigation drawer and closes it from the backdrop", async () => {
    render(<AdminLayout><div>admin content</div></AdminLayout>);
    await act(async () => { await Promise.resolve(); });

    const openButton = screen.getByRole("button", { name: "Open admin navigation" });
    expect(openButton.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(openButton);

    expect(screen.getByRole("button", { name: "Close admin navigation" }).getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Close admin navigation overlay" }));
    expect(screen.getByRole("button", { name: "Open admin navigation" }).getAttribute("aria-expanded")).toBe("false");
  });

  it("closes the mobile navigation after selecting a section", async () => {
    render(<AdminLayout><div>admin content</div></AdminLayout>);
    await act(async () => { await Promise.resolve(); });

    fireEvent.click(screen.getByRole("button", { name: "Open admin navigation" }));
    fireEvent.click(screen.getByRole("link", { name: "Client Installations" }));

    expect(screen.getByRole("button", { name: "Open admin navigation" }).getAttribute("aria-expanded")).toBe("false");
  });
});
