import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ apiFetch: vi.fn(), pathname: "/admin/settings" }));
vi.mock("@/lib/kodewavesApi", () => ({ apiFetch: mocks.apiFetch }));
vi.mock("next/navigation", () => ({ usePathname: () => mocks.pathname }));
vi.mock("next-themes", () => ({
  useTheme: () => ({ resolvedTheme: "light", setTheme: vi.fn() }),
}));

import { AuthShell } from "@/components/auth/AuthShell";
import { BrandLogo } from "@/components/BrandLogo";
import { PublicFooter } from "@/components/PublicSiteChrome";
import { DEFAULT_BRANDING } from "@/lib/branding";

import {
  ClientBrandingProvider,
  notifyBrandingChanged,
} from "./ClientBrandingContext";

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((index) => {
    const value = parseInt(hex.slice(index, index + 2), 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}

function contrastRatio(first: string, second: string): number {
  const [lighter, darker] = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
}

describe("shared platform branding", () => {
  beforeEach(() => {
    mocks.apiFetch.mockReset();
    mocks.pathname = "/admin/settings";
  });

  it("uses the configured brand in the superadmin panel title", async () => {
    mocks.pathname = "/superadmin/runs";
    const branding = { ...DEFAULT_BRANDING, company_name: "Acme Voice" };
    mocks.apiFetch.mockResolvedValue(branding);

    render(
      <ClientBrandingProvider initialBranding={branding}>
        <BrandLogo className="h-8" />
      </ClientBrandingProvider>,
    );

    await waitFor(() => expect(document.title).toBe("Superadmin | Acme Voice"));
  });

  it("retains the last brand when a refresh fails", async () => {
    const branding = { ...DEFAULT_BRANDING, company_name: "Acme Voice" };
    mocks.apiFetch.mockRejectedValue(new Error("Branding is temporarily unavailable"));
    render(<ClientBrandingProvider initialBranding={branding}><BrandLogo /></ClientBrandingProvider>);

    await waitFor(() => expect(mocks.apiFetch).toHaveBeenCalledTimes(1));
    act(() => notifyBrandingChanged());
    await waitFor(() => expect(mocks.apiFetch).toHaveBeenCalledTimes(2));
    expect(document.title).toBe("Admin | Acme Voice");
    expect(screen.getByText("Acme Voice")).toBeTruthy();
  });

  it("keeps a saved brand when an older refresh finishes afterward", async () => {
    let resolveInitial!: (value: typeof DEFAULT_BRANDING) => void;
    const initialRefresh = new Promise<typeof DEFAULT_BRANDING>((resolve) => {
      resolveInitial = resolve;
    });
    const savedBrand = { ...DEFAULT_BRANDING, company_name: "Saved Brand" };
    mocks.apiFetch
      .mockReturnValueOnce(initialRefresh)
      .mockResolvedValueOnce(savedBrand);

    render(
      <ClientBrandingProvider>
        <BrandLogo className="h-8" />
      </ClientBrandingProvider>,
    );
    act(() => notifyBrandingChanged());
    await waitFor(() => expect(document.title).toBe("Admin | Saved Brand"));

    await act(async () => resolveInitial(DEFAULT_BRANDING));

    expect(document.title).toBe("Admin | Saved Brand");
    expect(screen.getByText("Saved Brand")).toBeTruthy();
  });

  it("updates brand identity, support, browser title, icon and color after an admin save", async () => {
    const initial = {
      ...DEFAULT_BRANDING,
      company_name: "Acme Voice",
      tagline: "Acme conversations",
      support_email: "help@acme.example",
      primary_color: "#123456",
      favicon_url: "/acme.png",
      font: "system" as const,
    };
    mocks.apiFetch.mockResolvedValue(initial);
    render(
      <ClientBrandingProvider initialBranding={initial}>
        <BrandLogo className="h-8" />
        <PublicFooter />
        <AuthShell><p>Sign in form</p></AuthShell>
      </ClientBrandingProvider>,
    );
    expect(screen.getAllByText("Acme Voice").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Acme conversations" })).toBeTruthy();
    await waitFor(() => expect(document.title).toBe("Admin | Acme Voice"));
    expect(document.documentElement.style.getPropertyValue("--primary")).toBe(
      "#123456",
    );
    expect(
      contrastRatio(
        document.documentElement.style.getPropertyValue("--primary"),
        document.documentElement.style.getPropertyValue("--primary-foreground"),
      ),
    ).toBeGreaterThanOrEqual(4.5);
    const initialAccent = document.documentElement.style.getPropertyValue("--accent");
    expect(initialAccent).toMatch(/^#[0-9a-f]{6}$/i);
    expect(
      document.documentElement.style.getPropertyValue("--accent-foreground"),
    ).toMatch(/^#[0-9a-f]{6}$/i);
    expect(
      contrastRatio(
        initialAccent,
        document.documentElement.style.getPropertyValue("--accent-foreground"),
      ),
    ).toBeGreaterThanOrEqual(4.5);
    expect(document.documentElement.style.getPropertyValue("--brand-font-family")).toContain("system-ui");
    expect(
      screen
        .getByRole("link", { name: "Contact support" })
        .getAttribute("href"),
    ).toBe("mailto:help@acme.example");
    expect(
      document
        .querySelector<HTMLLinkElement>('link[rel="icon"]')
        ?.getAttribute("href"),
    ).toBe("/acme.png");
    mocks.apiFetch.mockResolvedValue({
      ...initial,
      company_name: "New Brand",
      tagline: "New conversations, with less busywork.",
      primary_color: "#654321",
    });
    act(() => notifyBrandingChanged());
    await waitFor(() => expect(document.title).toBe("Admin | New Brand"));
    expect(screen.getByRole("heading", {
      name: "New conversations, with less busywork.",
    })).toBeTruthy();
    expect(screen.queryByText("Acme Voice")).toBeNull();
    expect(screen.getAllByText("New Brand").length).toBeGreaterThan(0);
    expect(document.documentElement.style.getPropertyValue("--primary")).toBe(
      "#654321",
    );
    expect(document.documentElement.style.getPropertyValue("--accent")).not.toBe(
      initialAccent,
    );
    expect(
      contrastRatio(
        document.documentElement.style.getPropertyValue("--primary"),
        document.documentElement.style.getPropertyValue("--primary-foreground"),
      ),
    ).toBeGreaterThanOrEqual(4.5);
  });

  it("restores the configured browser title after framework metadata overwrites it", async () => {
    const configured = { ...DEFAULT_BRANDING, company_name: "Acme Voice" };
    mocks.apiFetch.mockReturnValue(new Promise(() => {}));
    render(<ClientBrandingProvider initialBranding={configured}><BrandLogo /></ClientBrandingProvider>);
    await waitFor(() => expect(document.title).toBe("Admin | Acme Voice"));

    act(() => { document.title = "Kodewaves"; });
    await waitFor(() => expect(document.title).toBe("Admin | Acme Voice"));
  });

});
