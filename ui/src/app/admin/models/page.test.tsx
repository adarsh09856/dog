import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  user: { id: "admin-1" },
  getMasterKeys: vi.fn(), getModels: vi.fn(), getAvailableCatalog: vi.fn(),
  saveMasterKey: vi.fn(), testMasterKey: vi.fn(), verifyProvider: vi.fn(), discoverProvider: vi.fn(),
  createModel: vi.fn(), updateModel: vi.fn(), deleteModel: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: mocks.user, loading: false }) }));
vi.mock("@/lib/kodewavesApi", () => ({ adminApi: mocks, catalogApi: { getAvailableCatalog: mocks.getAvailableCatalog } }));

import Page from "./page";

const model = {
  id: 31, provider: "openai", model_id: "gpt-4o-mini", display_name: "GPT mini",
  category: "llm" as const, cost_per_minute: 0.12, markup_margin_percent: 50,
  rate_per_minute: 0.18, is_active: true, is_default: false,
};
const catalog = {
  active_providers: ["openai"], cloud_llm_models: [], cloud_stt_models: [], cloud_tts_models: [],
  local_llm_models: [{ value: "qwen2.5", label: "Qwen 2.5" }], local_stt_models: [], local_tts_models: [],
  local_engine_enabled: true, has_local_ai_access: true,
};

beforeEach(() => {
  HTMLElement.prototype.scrollIntoView = vi.fn();
  mocks.getMasterKeys.mockReset().mockResolvedValue([]);
  mocks.getModels.mockReset().mockResolvedValue([model]);
  mocks.getAvailableCatalog.mockReset().mockResolvedValue(catalog);
  mocks.saveMasterKey.mockReset().mockResolvedValue({ message: "saved", id: 9 });
  mocks.testMasterKey.mockReset().mockResolvedValue({ success: true, message: "Connection successful", latency_ms: 42 });
  mocks.verifyProvider.mockReset().mockResolvedValue({ layers: {} });
  mocks.discoverProvider.mockReset().mockResolvedValue({ discovered_count: 1 });
  mocks.createModel.mockReset().mockResolvedValue(model);
  mocks.updateModel.mockReset().mockResolvedValue(model);
  mocks.deleteModel.mockReset().mockResolvedValue({ message: "deleted" });
});
afterEach(cleanup);

describe("Admin model workspace", () => {
  it("loads provider inventory and filters provider cards by capability", async () => {
    render(<Page />);
    expect(await screen.findByRole("heading", { name: "Models & provider access" })).toBeTruthy();
    expect(screen.getByText("Google Gemini")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Telecom (SIP Trunks)" }));
    expect(screen.getByText("Exotel Telephony")).toBeTruthy();
    expect(screen.queryByText("Google Gemini")).toBeNull();
  });

  it("filters the catalog by category and provider/model search", async () => {
    render(<Page />);
    fireEvent.mouseDown(await screen.findByRole("tab", { name: /Model Catalog/ }), { button: 0 });
    expect((await screen.findAllByText("GPT mini")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "TTS (Voice Studio)" }));
    expect(screen.getAllByText(/No models found matching current filter/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "All Models" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Search model catalog" }), { target: { value: "openai" } });
    expect((await screen.findAllByText("GPT mini")).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByRole("textbox", { name: "Search model catalog" }), { target: { value: "missing-provider" } });
    expect(screen.getAllByText(/No models found matching current filter/).length).toBeGreaterThan(0);
  });

  it("keeps provider tests scoped to configured keys and shows their result", async () => {
    mocks.getMasterKeys.mockResolvedValue([{ provider: "openai", category: "llm", display_name: "OpenAI", api_key_masked: "sk-••••last", has_credentials: true, is_active: true, status: "active" }]);
    render(<Page />);
    const provider = await screen.findByText("OpenAI");
    const card = provider.closest("[class*='providerCard']");
    expect(card).toBeTruthy();
    const testButton = within(card as HTMLElement).getByRole("button", { name: "Test" });
    expect(testButton.hasAttribute("disabled")).toBe(false);
    fireEvent.click(testButton);
    expect(await screen.findByText("Connection successful")).toBeTruthy();
    expect(mocks.testMasterKey).toHaveBeenCalledWith("openai");
  });

  it("saves provider credentials without rendering or retaining entered secret values", async () => {
    render(<Page />);
    const exotel = await screen.findByText("Exotel Telephony");
    fireEvent.click(within(exotel.closest("[class*='providerCard']") as HTMLElement).getByRole("button", { name: "Configure" }));
    fireEvent.change(screen.getByPlaceholderText("Enter API key"), { target: { value: "private-api-token" } });
    fireEvent.change(screen.getByPlaceholderText("Enter API Secret"), { target: { value: "private-api-secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Credential" }));
    await waitFor(() => expect(mocks.saveMasterKey).toHaveBeenCalledWith(expect.objectContaining({
      provider: "exotel", api_key: "private-api-token", api_secret: "private-api-secret",
      credentials: expect.objectContaining({ api_key: "private-api-token", api_secret: "private-api-secret" }),
    })));
    await waitFor(() => expect(screen.queryByDisplayValue("private-api-token")).toBeNull());
    expect(screen.queryByDisplayValue("private-api-secret")).toBeNull();
  });

  it("creates a catalog entry through the existing save flow", async () => {
    render(<Page />);
    fireEvent.mouseDown(await screen.findByRole("tab", { name: /Model Catalog/ }), { button: 0 });
    fireEvent.click(screen.getByRole("button", { name: "Add Catalog Entry" }));
    fireEvent.change(screen.getByPlaceholderText("e.g. sarvam, openai, elevenlabs"), { target: { value: "openai" } });
    fireEvent.change(screen.getByPlaceholderText("e.g. High Performance Indic Voice"), { target: { value: "GPT test" } });
    fireEvent.change(screen.getByPlaceholderText("e.g. llama-3.3-70b-versatile, gpt-4o-mini"), { target: { value: "gpt-test" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Model" }));
    await waitFor(() => expect(mocks.createModel).toHaveBeenCalledWith(expect.objectContaining({
      provider: "openai", display_name: "GPT test", model_id: "gpt-test",
    })));
  });
});
