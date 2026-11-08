import { fireEvent, render, screen } from "@testing-library/react";
import type { AnchorHTMLAttributes } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props} />
  ),
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
vi.mock("next-themes", () => ({
  useTheme: () => ({ resolvedTheme: "dark", setTheme: vi.fn() }),
}));
vi.mock("@/components/BrandLogo", () => ({
  BrandLogo: () => <span aria-hidden="true">Brand</span>,
}));
vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: () => ({
    company_name: "Acme Voice",
    tagline: "Voice tools for Acme.",
    support_email: "help@acme.example",
  }),
}));

import { PublicHeader } from "./PublicSiteChrome";

describe("public site navigation", () => {
  it("offers use cases and a clear workspace entry on mobile, and closes on Escape", () => {
    render(<PublicHeader />);

    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    const mobileNavigation = screen.getByRole("navigation", { name: "Mobile navigation" });
    expect(mobileNavigation.querySelector('a[href="/#scenarios"]')?.textContent).toBe("Use cases");
    expect(mobileNavigation.querySelector('a[href="/auth/login"]')?.textContent).toContain("Open workspace");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("navigation", { name: "Mobile navigation" })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Open navigation" }));
  });
});
