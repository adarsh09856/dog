import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ apiFetch: vi.fn(), copy: vi.fn(), useAuth: vi.fn() }));

vi.mock("@/lib/kodewavesApi", () => ({ apiFetch: mocks.apiFetch }));
vi.mock("@/lib/clipboard", () => ({ copyTextToClipboard: mocks.copy }));
vi.mock("@/lib/auth", () => ({ useAuth: mocks.useAuth }));

import ApiKeysPage from "./page";

describe("workspace API key settings", () => {
  beforeEach(() => {
    mocks.apiFetch.mockReset();
    mocks.copy.mockReset();
    mocks.useAuth.mockReset();
    mocks.useAuth.mockReturnValue({ loading: false, user: { id: 1 } });
    mocks.apiFetch.mockImplementation((endpoint: string, options?: RequestInit) => {
      if (endpoint.startsWith("/user/api-keys?")) return Promise.resolve([]);
      if (endpoint === "/user/api-keys" && options?.method === "POST") {
        return Promise.resolve({
          id: 41,
          name: "Production integration",
          key_prefix: "kw_live_",
          api_key: "kw_live_secret_once",
          is_active: true,
          created_at: "2026-10-25T00:00:00Z",
        });
      }
      return Promise.resolve({});
    });
  });

  it("waits for authentication before loading workspace keys", async () => {
    mocks.useAuth.mockReturnValue({ loading: true, user: null });
    const { rerender } = render(<ApiKeysPage />);

    expect(mocks.apiFetch).not.toHaveBeenCalled();

    mocks.useAuth.mockReturnValue({ loading: false, user: { id: 1 } });
    rerender(<ApiKeysPage />);

    await waitFor(() => expect(mocks.apiFetch).toHaveBeenCalledWith("/user/api-keys?include_archived=true"));
  });

  it("creates a key and shows its secret only in the one-time creation result", async () => {
    render(<ApiKeysPage />);

    fireEvent.change(await screen.findByRole("textbox", { name: "API key name" }), {
      target: { value: "Production integration" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create key" }));

    expect(await screen.findByText("kw_live_secret_once")).toBeTruthy();
    expect(screen.getByText(/It will not be shown again/)).toBeTruthy();
    expect(mocks.apiFetch).toHaveBeenCalledWith("/user/api-keys", {
      method: "POST",
      body: JSON.stringify({ name: "Production integration" }),
    });
    expect(mocks.apiFetch).toHaveBeenCalledWith("/user/api-keys?include_archived=true");
  });

  it("surfaces API failures and lets the user retry loading", async () => {
    mocks.apiFetch
      .mockRejectedValueOnce(new Error("workspace unavailable"))
      .mockResolvedValueOnce([]);
    render(<ApiKeysPage />);

    expect(await screen.findByText("workspace unavailable")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Refresh API keys" }));
    await waitFor(() => expect(screen.getByText(/No API keys have been created/)).toBeTruthy());
  });
});
