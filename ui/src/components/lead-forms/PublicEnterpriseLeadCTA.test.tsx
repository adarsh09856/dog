import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const useClientBrandingMock = vi.hoisted(() => vi.fn());

vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: useClientBrandingMock,
}));

vi.mock("./EnterpriseModal", () => ({
  EnterpriseModal: ({ open, source }: { open: boolean; source: string }) =>
    open ? <div role="dialog" data-source={source}>Enterprise intake</div> : null,
}));

import { PublicEnterpriseLeadCTA } from "./PublicEnterpriseLeadCTA";

describe("PublicEnterpriseLeadCTA", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_KODEWAVES_EDITION", "saas");
    vi.stubEnv("NEXT_PUBLIC_ONBOARDING_API_URL", "https://onboarding.example.test");
    useClientBrandingMock.mockReturnValue({ company_name: "Kodewaves", support_email: "" });
  });

  it("keeps the hosted enterprise intake in the SaaS edition", () => {
    render(<PublicEnterpriseLeadCTA label="Discuss a client installation" className="cta" />);

    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Discuss a client installation/ }));

    expect(screen.getByRole("dialog").getAttribute("data-source")).toBe("landing_contact");
  });

  it("routes client enquiries to the installation support email", () => {
    vi.stubEnv("NEXT_PUBLIC_KODEWAVES_EDITION", "client");
    useClientBrandingMock.mockReturnValue({ company_name: "Acme Voice", support_email: "voice-support@acme.example" });

    render(<PublicEnterpriseLeadCTA label="Discuss this installation" className="cta" />);

    expect(screen.getByRole("link", { name: /Discuss this installation/ }).getAttribute("href")).toBe(
      "mailto:voice-support@acme.example?subject=Installation%20enquiry",
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("explains how to reach the administrator when no support email is configured", () => {
    vi.stubEnv("NEXT_PUBLIC_KODEWAVES_EDITION", "client");

    render(<PublicEnterpriseLeadCTA label="Discuss this installation" className="cta" />);

    expect(screen.getByRole("note").textContent).toContain("Contact your installation administrator");
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("routes hosted enquiries to the support email when the lead service is not configured", () => {
    vi.stubEnv("NEXT_PUBLIC_ONBOARDING_API_URL", "");
    useClientBrandingMock.mockReturnValue({ company_name: "Kodewaves", support_email: "sales@kodewaves.in" });

    render(<PublicEnterpriseLeadCTA label="Talk to sales" className="cta" />);

    expect(screen.getByRole("link", { name: /Talk to sales/ }).getAttribute("href")).toBe(
      "mailto:sales@kodewaves.in?subject=Enterprise%20enquiry",
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("does not expose a broken lead form when neither the service nor a support email is configured", () => {
    vi.stubEnv("NEXT_PUBLIC_ONBOARDING_API_URL", "");
    useClientBrandingMock.mockReturnValue({ company_name: "Kodewaves", support_email: "" });

    render(<PublicEnterpriseLeadCTA label="Talk to sales" className="cta" />);

    expect(screen.getByRole("note").textContent).toContain("Enterprise enquiries are not configured");
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
