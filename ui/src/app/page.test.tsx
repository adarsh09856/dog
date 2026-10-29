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

    expect(screen.getByRole("main").textContent).toContain(
      "Acme helps every caller take the next step.",
    );
    expect(screen.getByRole("main").textContent).toContain(
      "Acme Voice voice agent workspace",
    );
    expect(screen.getByRole("main").textContent).not.toContain("Kodewaves");
    expect(screen.getByRole("contentinfo").textContent).toContain(
      "Acme helps every caller take the next step.",
    );
  });

  it("describes the product lifecycle and labels its workflow schematic as illustrative", () => {
    render(<HomePage />);

    const heroHeading = screen.getByRole("heading", { level: 1 });
    expect(heroHeading.textContent).toContain("Every conversation.");
    expect(heroHeading.textContent).toContain("A clear next step.");
    expect(screen.getByText("Configure the full call lifecycle")).toBeTruthy();
    expect(screen.getByText("Workflow builder")).toBeTruthy();
    expect(screen.getByText("Web and telephone")).toBeTruthy();
    expect(screen.getByText("Conversation review")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Shape the work before the call." })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Choose how people reach you." })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Review what happened." })).toBeTruthy();
    expect(screen.getByLabelText("Illustration of a voice workflow from caller to action")).toBeTruthy();
    expect(screen.getByText("Illustrative workflow")).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Conversation examples" })).toBeNull();
  });
});
