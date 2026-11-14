import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ getStats: vi.fn() }));

vi.mock("@/lib/kodewavesApi", () => ({
  adminApi: { getStats: mocks.getStats },
}));
vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: () => ({ company_name: "Kodewaves" }),
}));

import AdminDashboardPage from "./page";

describe("superadmin dashboard database status", () => {
  beforeEach(() => mocks.getStats.mockReset());
  afterEach(() => vi.restoreAllMocks());

  it("reports connected only after live telemetry loads", async () => {
    mocks.getStats.mockResolvedValue({
      total_calls: 0,
      active_calls: 0,
      completed_calls: 0,
      total_minutes: 0,
      total_revenue_inr: null,
      gross_margin_percent: null,
      system_health: "healthy",
    });

    const view = render(<AdminDashboardPage />);

    expect(await screen.findByText("Database connected")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Sovereign Control Plane" })).toBeTruthy();
    view.unmount();
  });

  it("shows the global owner controls separately from workspace administration", async () => {
    mocks.getStats.mockResolvedValue({
      total_calls: 12,
      active_calls: 1,
      completed_calls: 11,
      total_minutes: 42,
      total_revenue_inr: null,
      gross_margin_percent: null,
      system_health: "healthy",
    });

    const view = render(<AdminDashboardPage />);

    expect(await screen.findByText("Database connected")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Client installations & releases/ }).getAttribute("href"))
      .toBe("/superadmin/client-installations");
    expect(screen.getByRole("link", { name: /Platform identity & public branding/ }).getAttribute("href"))
      .toBe("/superadmin/settings");
    expect(screen.getByRole("link", { name: /Self-hosted voice stack/ }).getAttribute("href"))
      .toBe("/superadmin/settings#settings-local-ai");
    expect(screen.getByRole("link", { name: /Customer workspace access/ }).getAttribute("href"))
      .toBe("/superadmin/access");
    expect(screen.getByRole("link", { name: /Access & usage policies/ }).getAttribute("href"))
      .toBe("/superadmin/settings#settings-policies");
    expect(screen.getByRole("link", { name: /Local model inventory/ }).getAttribute("href"))
      .toBe("/superadmin/settings#settings-ollama");
    expect(screen.getByRole("link", { name: /Speech recognition \(STT\)/ }).getAttribute("href"))
      .toBe("/superadmin/settings#settings-stt");
    expect(screen.getByRole("link", { name: /Speech generation \(TTS\)/ }).getAttribute("href"))
      .toBe("/superadmin/settings#settings-tts");
    expect(screen.getByRole("link", { name: /Brand & public identity/ }).getAttribute("href"))
      .toBe("/superadmin/settings#settings-branding");
    expect(screen.getByRole("link", { name: /Email delivery/ }).getAttribute("href"))
      .toBe("/superadmin/settings#settings-email");
    expect(screen.getByRole("link", { name: /Payment providers/ }).getAttribute("href"))
      .toBe("/superadmin/settings#settings-payments");
    expect(screen.getByRole("link", { name: /Content moderation/ }).getAttribute("href"))
      .toBe("/superadmin/moderation");
    expect(screen.getByText(/Customer workspaces keep their own business admin at/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Workspace settings/ })).toBeNull();
    view.unmount();
  });
});
