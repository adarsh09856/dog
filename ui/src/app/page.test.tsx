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
    expect(heroHeading.textContent).toContain("AI voice agents for calls.");
    expect(heroHeading.textContent).toContain("Workflows that get things done.");
    expect(screen.getByText("Configure the full call lifecycle")).toBeTruthy();
    expect(screen.getByText("Workflow builder")).toBeTruthy();
    expect(screen.getByText("Inbound and outbound calls")).toBeTruthy();
    expect(screen.getByText("Outbound campaigns")).toBeTruthy();
    expect(screen.getByText("CRM and appointments")).toBeTruthy();
    expect(screen.getByText("Voice forms and web widgets")).toBeTruthy();
    expect(screen.getByText("Tools and knowledge")).toBeTruthy();
    expect(screen.getByText("Configured speech models")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Build the voice agent workflow." })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Connect browser and phone calls." })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Review each call and run." })).toBeTruthy();
    expect(screen.getByLabelText(/inbound, outbound and browser voice calls/)).toBeTruthy();
    expect(screen.getByText("Inbound")).toBeTruthy();
    expect(screen.getByText("Outbound")).toBeTruthy();
    expect(screen.getByText("Browser")).toBeTruthy();
    expect(screen.getByText("01 / STT")).toBeTruthy();
    expect(screen.getByText("02 / LLM")).toBeTruthy();
    expect(screen.getByText("03 / TTS")).toBeTruthy();
    expect(screen.getByText("Context · knowledge · tools")).toBeTruthy();
    expect(screen.getByText("Run details, transcript and recording")).toBeTruthy();
    expect(screen.getByText(/Illustrative flow/)).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Conversation examples" })).toBeNull();
  });

  it("keeps the homepage hero description readable on the dark hero background", () => {
    render(<HomePage />);

    const description = screen.getByText(/Answer inbound calls, run outbound campaigns/);
    expect(description.className).toContain("heroDescription");
  });
});
