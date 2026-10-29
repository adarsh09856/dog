import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getSettings: vi.fn(),
  getOllamaModels: vi.fn(),
  apiFetch: vi.fn(),
  notifyBrandingChanged: vi.fn(),
  user: { id: "admin-1" },
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: mocks.user, loading: false }) }));
vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: () => ({ primary_color: "#426b57" }),
  notifyBrandingChanged: mocks.notifyBrandingChanged,
}));
vi.mock("@/lib/kodewavesApi", () => ({
  adminApi: { getSettings: mocks.getSettings, getOllamaModels: mocks.getOllamaModels },
  apiFetch: mocks.apiFetch,
}));
vi.mock("./IndicSttTest", () => ({ default: () => null }));

import AdminSettingsPage from "./page";

afterEach(() => cleanup());
beforeEach(() => {
  vi.clearAllMocks();
  mocks.getSettings.mockResolvedValue({ company_name: "Kodewaves", tagline: "Voice agents" });
  mocks.getOllamaModels.mockResolvedValue({ models: [], status: "online" });
  mocks.apiFetch.mockResolvedValue({});
});

it("saves the platform branding and refreshes shared branding", async () => {
  render(<AdminSettingsPage />);

  const brandName = await screen.findByLabelText("Company / Brand Name");
  fireEvent.change(brandName, { target: { value: "Acme Voice" } });
  fireEvent.click(screen.getByRole("button", { name: "Save branding" }));

  await waitFor(() => expect(mocks.apiFetch).toHaveBeenCalledWith("/installation/branding", expect.objectContaining({
    method: "PUT",
    body: expect.any(String),
  })));
  const [, request] = mocks.apiFetch.mock.calls[0];
  expect(JSON.parse(request.body)).toMatchObject({
    company_name: "Acme Voice",
    tagline: "Voice agents",
    primary_color: "#426b57",
  });
  expect(mocks.notifyBrandingChanged).toHaveBeenCalledTimes(1);
  expect((await screen.findByRole("status")).textContent).toContain("Branding updated across the platform.");
});
