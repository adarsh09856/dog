import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ pathname: "/", fetch: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => state.pathname }));
vi.mock("@/lib/logger", () => ({ default: { debug: vi.fn(), error: vi.fn() } }));
vi.mock("../LocalProviderWrapper", () => ({ LocalProviderWrapper: ({ children }: { children: React.ReactNode }) => <div data-testid="authenticated-provider">{children}</div> }));

import { AuthProvider, useAuth } from "../AuthProvider";

function Probe() {
  const auth = useAuth();
  return <p>{auth.provider}: {auth.isAuthenticated ? "authenticated" : "guest"}</p>;
}

describe("public-page authentication boundary", () => {
  beforeEach(() => {
    state.fetch.mockReset();
    vi.stubGlobal("fetch", state.fetch);
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it.each(["/", "/pricing", "/auth/login", "/auth/signup"])("renders %s immediately without an auth-config request", (pathname) => {
    state.pathname = pathname;
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(screen.getByText("public: guest")).toBeTruthy();
    expect(state.fetch).not.toHaveBeenCalled();
    expect(screen.queryByTestId("authenticated-provider")).toBeNull();
  });

  it.each(["/workflow", "/admin/settings", "/pricing-private"])("keeps the real authentication bootstrap for %s", async (pathname) => {
    state.pathname = pathname;
    state.fetch.mockResolvedValue({ json: async () => ({ provider: "local" }) });
    render(<AuthProvider><span>Private page content</span></AuthProvider>);
    expect(state.fetch).toHaveBeenCalledWith("/api/config/auth");
    expect(await screen.findByTestId("authenticated-provider")).toBeTruthy();
  });
});
