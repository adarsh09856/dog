import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: () => ({
    company_name: "Kodewaves",
    tagline: "Conversations that move work forward.",
  }),
}));

vi.mock("@/components/BrandLogo", () => ({
  BrandLogo: () => <span>Kodewaves</span>,
}));

import { AuthShell } from "./AuthShell";

describe("AuthShell", () => {
  it("keeps a branded, accessible product introduction available on narrow layouts", () => {
    render(
      <AuthShell>
        <h1>Sign in</h1>
      </AuthShell>,
    );

    expect(screen.getByRole("region", { name: "Voice operations overview" })).toBeTruthy();
    expect(screen.getAllByText("Conversations that move work forward.")).toHaveLength(2);
    expect(screen.getByText(/Build the conversation, connect your channels/)).toBeTruthy();
    expect(screen.getByRole("main").getAttribute("id")).toBe("main-content");
    expect(screen.getByRole("link", { name: "Back to site" })).toBeTruthy();
  });
});
