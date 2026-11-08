import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: () => ({ company_name: "Kodewaves", logo_url: null }),
}));

import { BrandLogo } from "./BrandLogo";

describe("BrandLogo", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllEnvs();
  });

  it("uses a light wordmark when shown on the dark workspace sidebar", () => {
    render(<BrandLogo inverse />);

    expect(screen.getByText("Kodewaves").className).toContain("text-white");
  });

  it("keeps the standard foreground wordmark on light surfaces", () => {
    render(<BrandLogo />);

    expect(screen.getByText("Kodewaves").className).toContain("text-foreground");
  });

  it("uses a generic voice mark for client editions without a configured logo", () => {
    vi.stubEnv("NEXT_PUBLIC_KODEWAVES_EDITION", "client");
    render(<BrandLogo />);

    expect(screen.getByTestId("generic-brand-mark")).toBeTruthy();
    expect(screen.getByTestId("generic-brand-mark").querySelector("svg")).toBeTruthy();
  });

  it("keeps the Kodewaves mark in the SaaS edition", () => {
    vi.stubEnv("NEXT_PUBLIC_KODEWAVES_EDITION", "saas");
    const { container } = render(<BrandLogo />);

    expect(screen.queryByTestId("generic-brand-mark")).toBeNull();
    expect(container.querySelector("linearGradient#kodewaves-brand-gradient")).toBeTruthy();
  });
});
