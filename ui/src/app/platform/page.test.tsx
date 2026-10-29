import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/PublicSiteChrome", () => ({
  PublicHeader: () => <header>Public navigation</header>,
  PublicFooter: () => <footer>Public footer</footer>,
}));

import PlatformPage from "./page";

describe("public platform page", () => {
  it("explains the end-to-end voice operations workflow and links into the product", () => {
    render(<PlatformPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("first prompt");
    expect(screen.getByRole("heading", { name: "Build, connect, test, learn." })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "CRM and appointments" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open workspace/ }).getAttribute("href")).toBe("/auth/login");
    expect(screen.getByRole("link", { name: "View plans" }).getAttribute("href")).toBe("/pricing");
  });
});
