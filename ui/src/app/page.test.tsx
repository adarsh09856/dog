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
    expect(screen.getByRole("contentinfo").textContent).toContain(
      "Acme helps every caller take the next step.",
    );
  });

  it("describes the real agent lifecycle without a fabricated conversation preview", () => {
    render(<HomePage />);

    expect(screen.getByRole("heading", { name: "Build, test and operate voice agents." })).toBeTruthy();
    expect(screen.getByText("Operating lifecycle")).toBeTruthy();
    expect(screen.getByText("Test the conversation")).toBeTruthy();
    expect(screen.getByText("Operate and improve")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Shape the work before the call." })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Choose how people reach you." })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Review what happened." })).toBeTruthy();
    expect(screen.queryByText("Illustrative workflow")).toBeNull();
    expect(screen.queryByRole("group", { name: "Conversation examples" })).toBeNull();
  });
});
