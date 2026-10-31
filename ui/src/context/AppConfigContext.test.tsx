import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const clientMocks = vi.hoisted(() => ({ setConfig: vi.fn() }));
vi.mock("@/client/client.gen", () => ({ client: { setConfig: clientMocks.setConfig } }));
vi.mock("@/lib/apiClient", () => ({ resolveBrowserBackendUrl: (url: string) => url }));

import { AppConfigProvider, useAppConfig } from "./AppConfigContext";

function BackendStatus() {
  const { config } = useAppConfig();
  return <span>{config?.backendStatus ?? "loading"}</span>;
}

describe("AppConfigProvider backend recovery", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    clientMocks.setConfig.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("rechecks an unreachable backend and clears the stale state after recovery", async () => {
    fetchMock
      .mockRejectedValueOnce(new Error("temporary outage"))
      .mockResolvedValueOnce({
        json: async () => ({
          ui: "1.47.0",
          api: "1.47.0",
          backend: { status: "reachable", url: "http://api:8000" },
          backendApiEndpoint: "https://api.example.test",
        }),
      });

    render(<AppConfigProvider><BackendStatus /></AppConfigProvider>);

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByText("unreachable")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(screen.getByText("reachable")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);

    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
