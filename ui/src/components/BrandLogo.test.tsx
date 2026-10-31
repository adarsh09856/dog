import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: () => ({ company_name: "Kodewaves", logo_url: null }),
}));

import { BrandLogo } from "./BrandLogo";

describe("BrandLogo", () => {
  it("uses a light wordmark when shown on the dark workspace sidebar", () => {
    render(<BrandLogo inverse />);

    expect(screen.getByText("Kodewaves").className).toContain("text-white");
  });

  it("keeps the standard foreground wordmark on light surfaces", () => {
    render(<BrandLogo />);

    expect(screen.getByText("Kodewaves").className).toContain("text-foreground");
  });
});
