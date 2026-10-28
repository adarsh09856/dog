import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ getStats: vi.fn() }));

vi.mock("@/lib/kodewavesApi", () => ({
  overviewApi: { getStats: mocks.getStats },
}));
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: { displayName: "Alex Example", is_superuser: false },
    loading: false,
  }),
}));
vi.mock("@/context/ClientBrandingContext", () => ({
  useClientBranding: () => ({ company_name: "Acme Voice" }),
}));

import OverviewPage from "./page";

const emptyStats = {
  wallet: { credit_balance_minutes: 0, bonus_minutes: 0, total_minutes: 0 },
  calls: { active_calls: 0, calls_today: 0, calls_this_week: 0, success_rate_percent: 100 },
  agents: { active_agents_count: 0, total_agents_count: 0 },
  recent_runs: [],
  model_health: {
    has_llm: false,
    has_stt: false,
    has_tts: false,
    has_s2s: false,
    total_models: 0,
    warnings: [],
  },
};

describe("workspace overview", () => {
  beforeEach(() => mocks.getStats.mockReset());

  it("does not present an empty call history as a 100 percent success rate", async () => {
    mocks.getStats.mockResolvedValue(emptyStats);
    render(<OverviewPage />);

    expect(await screen.findByText("no calls yet")).toBeTruthy();
    expect(screen.getByText("—")).toBeTruthy();
    expect(screen.queryByText("100%" )).toBeNull();
    expect(screen.getByText("No model availability warnings.")).toBeTruthy();
    expect(screen.queryByText(/All Voice AI Layers Operational/)).toBeNull();
  });

  it("routes model warnings to tenant model configuration", async () => {
    mocks.getStats.mockResolvedValue({
      ...emptyStats,
      model_health: {
        ...emptyStats.model_health,
        warnings: ["No active LLM model is available."],
      },
    });
    render(<OverviewPage />);

    const configureLink = await screen.findByRole("link", { name: "Configure models" });
    expect(configureLink.getAttribute("href")).toBe("/model-configurations");
  });

  it("uses the configured brand theme for overview capability and wallet accents", async () => {
    mocks.getStats.mockResolvedValue(emptyStats);
    render(<OverviewPage />);

    const topUp = await screen.findByRole("link", { name: "Top Up" });
    expect(topUp.querySelector("svg")?.classList.contains("text-primary")).toBe(true);

    const deployment = screen.getByText("Hosted or customer-managed deployment");
    expect(deployment.querySelector("svg")?.classList.contains("text-primary")).toBe(true);

    const voiceMinutes = screen.getByText("Voice Minutes").parentElement?.parentElement;
    const walletIcon = voiceMinutes?.querySelector(".h-8.w-8");
    expect(walletIcon?.classList.contains("bg-primary/10")).toBe(true);
    expect(walletIcon?.classList.contains("text-primary")).toBe(true);
  });
});
