import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/PublicSiteChrome", () => ({
  PublicHeader: () => <header>Public navigation</header>,
  PublicFooter: () => <footer>Public footer</footer>,
}));
vi.mock("@/components/lead-forms/PublicEnterpriseLeadCTA", () => ({
  PublicEnterpriseLeadCTA: ({ label }: { label: string }) => <button type="button">{label}</button>,
}));

import DeploymentPage from "./page";

describe("public deployment page", () => {
  it("describes managed and client installation options without promising fixed latency", () => {
    render(<DeploymentPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("where your voice operations run");
    expect(screen.getByRole("heading", { name: "Managed workspace" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Client installation" })).toBeTruthy();
    expect(screen.getByText(/No fixed performance target is implied/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Discuss a client installation" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Review plans and costs" }).getAttribute("href")).toBe("/pricing");
  });
});
