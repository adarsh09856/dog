import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/PublicSiteChrome", () => ({
  PublicHeader: () => <header>Public navigation</header>,
  PublicFooter: () => <footer>Public footer</footer>,
}));
vi.mock("@/components/lead-forms/PublicEnterpriseLeadCTA", () => ({
  PublicEnterpriseLeadCTA: ({ label }: { label: string }) => <button type="button">{label}</button>,
}));

import DeploymentPage, { metadata } from "./page";

describe("public deployment page", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("sets a page-specific browser title and search description", () => {
    expect(metadata.title).toBe("Deployment");
    expect(metadata.description).toContain("licensed client installations");
  });

  it("describes managed and client installation options without promising fixed latency", () => {
    render(<DeploymentPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("where your voice operations run");
    expect(screen.getByRole("heading", { name: "Managed workspace" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Client installation" })).toBeTruthy();
    expect(screen.getByText(/No fixed performance target is implied/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Discuss a client installation" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Review plans and costs" }).getAttribute("href")).toBe("/pricing");
  });

  it("discloses client license-check metadata and customer/provider data boundaries", () => {
    render(<DeploymentPage />);
    expect(screen.getByRole("heading", { name: "Client installation data and license checks" })).toBeTruthy();
    expect(screen.getByText(/owner service receives the installation identity, the requester.s observed IP address, and the integrity-check result or finding, then returns signed license status/)).toBeTruthy();
    expect(screen.getByText(/The check payload sent to the owner service does not include call audio or conversation transcripts/)).toBeTruthy();
    expect(screen.getByText(/location of the database and recordings depends on the services and storage provisioned for the customer.s installation/)).toBeTruthy();
    expect(screen.getByText(/Connected telephony, speech, model and business providers may process call data/)).toBeTruthy();
  });

  it("keeps client-edition deployment content scoped to the customer's installation", () => {
    vi.stubEnv("NEXT_PUBLIC_KODEWAVES_EDITION", "client");
    render(<DeploymentPage />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Your voice operations environment");
    expect(screen.getByRole("heading", { name: "Client installation" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Managed workspace" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Discuss a client installation" })).toBeNull();
    expect(screen.queryByText(/Kodewaves/i)).toBeNull();
    expect(screen.getByText(/platform owner service receives the installation identity/)).toBeTruthy();
    expect(screen.queryByText("Two operating models")).toBeNull();
    expect(screen.queryByText(/Both use the same workflow concepts/)).toBeNull();
    expect(screen.queryByText(/Hosted workspace or customer-managed environment/)).toBeNull();
    expect(screen.getByRole("heading", { name: "Your licensed installation." })).toBeTruthy();
  });
});
