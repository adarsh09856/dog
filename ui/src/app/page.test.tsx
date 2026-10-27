import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
vi.mock("next-themes", () => ({
  useTheme: () => ({ resolvedTheme: "light", setTheme: vi.fn() }),
}));
vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: () => ({
    company_name: "Acme Voice",
    tagline: "Acme helps every caller take the next step.",
    logo_url: "",
    primary_color: "#304c73",
  }),
}));

import HomePage from "./page";

describe("public home branding", () => {
  it("uses the admin-configured brand tagline in the hero", () => {
    render(<HomePage />);

    expect(
      screen.getAllByText("Acme helps every caller take the next step."),
    ).toHaveLength(2);
  });
});
