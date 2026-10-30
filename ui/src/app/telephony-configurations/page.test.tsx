import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ list: vi.fn() }));

vi.mock("@/client/sdk.gen", () => ({
  listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet: mocks.list,
  getTelephonyConfigurationByIdApiV1OrganizationsTelephonyConfigsConfigIdGet: vi.fn(),
  setDefaultOutboundApiV1OrganizationsTelephonyConfigsConfigIdSetDefaultOutboundPost: vi.fn(),
  reactivateTelephonyConfigurationApiV1OrganizationsTelephonyConfigsConfigIdReactivatePost: vi.fn(),
  deleteTelephonyConfigurationApiV1OrganizationsTelephonyConfigsConfigIdDelete: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 7 }, getAccessToken: async () => "token", loading: false }) }));
vi.mock("@/context/TelephonyConfigWarningsContext", () => ({
  useTelephonyConfigWarnings: () => ({ telnyxMissingWebhookPublicKeyCount: 0, vonageMissingSignatureSecretCount: 0, refresh: vi.fn() }),
}));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));
vi.mock("@/components/telephony/ConfigFormDialog", () => ({
  ConfigFormDialog: ({ open }: { open: boolean }) => open ? <div role="dialog" aria-label="Provider configuration form" /> : null,
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import TelephonyConfigurationsPage from "./page";

describe("telephony workspace", () => {
  beforeEach(() => {
    mocks.list.mockReset().mockResolvedValue({
      data: {
        configurations: [{
          id: 12,
          name: "Primary Twilio",
          provider: "twilio",
          phone_number_count: 2,
          is_default_outbound: true,
          inactive: false,
          is_ready_for_outbound: true,
        }],
      },
    });
  });

  it("shows provider readiness, phone inventory, and management route", async () => {
    render(<TelephonyConfigurationsPage />);

    expect(await screen.findByText("Primary Twilio")).toBeTruthy();
    expect(screen.getByText("Ready for outbound").parentElement?.textContent).toContain("1");
    expect(screen.getByText("Phone numbers").parentElement?.textContent).toContain("2");
    expect(screen.getByRole("link", { name: "Manage phone numbers for Primary Twilio" }).getAttribute("href"))
      .toBe("/telephony-configurations/12");
  });

  it("keeps the add-provider action connected to the existing form flow", async () => {
    render(<TelephonyConfigurationsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Add configuration" }));
    expect(await screen.findByRole("dialog", { name: "Provider configuration form" })).toBeTruthy();
  });
});
