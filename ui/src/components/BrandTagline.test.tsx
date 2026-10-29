import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: () => ({ tagline: "Conversations that move work forward" }),
}));

import { BrandTagline } from "./BrandTagline";

describe("BrandTagline", () => {
  it("renders the admin-configured platform tagline", () => {
    render(<BrandTagline className="workspace-tagline" />);

    expect(screen.getByText("Conversations that move work forward").className)
      .toBe("workspace-tagline");
  });
});
