import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("@/lib/logger", () => ({ default: { info: vi.fn(), error: vi.fn(), warn: vi.fn() } }));

import { useAuth } from "../AuthProvider";
import { LocalProviderWrapper } from "../LocalProviderWrapper";

function AuthProbe() {
  const auth = useAuth();
  return <p>{auth.provider}: {auth.loading ? "loading" : auth.isAuthenticated ? "authenticated" : "guest"}</p>;
}

const originalLocationDescriptor = Object.getOwnPropertyDescriptor(window, "location");
let testLocation: { pathname: string; search: string; href: string };

function setTestLocation(pathname: string, search = "") {
  testLocation = { pathname, search, href: `https://kodewaves.example${pathname}${search}` };
  Object.defineProperty(window, "location", { configurable: true, value: testLocation });
}

describe("LocalProviderWrapper public routes", () => {
  beforeEach(() => {
    state.fetch.mockReset();
    state.fetch.mockResolvedValue({ ok: false, status: 401 });
    vi.stubGlobal("fetch", state.fetch);
  });

  afterEach(() => {
    cleanup();
    if (originalLocationDescriptor) {
      Object.defineProperty(window, "location", originalLocationDescriptor);
    }
    vi.unstubAllGlobals();
  });

  it.each(["/platform", "/deployment"])("renders %s without redirecting on the OSS 401 response", async (pathname) => {
    setTestLocation(pathname, "?source=marketing");

    render(<LocalProviderWrapper><AuthProbe /></LocalProviderWrapper>);

    expect(await screen.findByText("local: guest")).toBeTruthy();
    await waitFor(() => expect(state.fetch).toHaveBeenCalledWith("/api/auth/oss"));
    expect(testLocation.href).toBe(`https://kodewaves.example${pathname}?source=marketing`);
  });

  it("still redirects a protected route after an OSS 401 response", async () => {
    setTestLocation("/workflow", "?tab=recent");

    render(<LocalProviderWrapper><AuthProbe /></LocalProviderWrapper>);

    await waitFor(() => expect(testLocation.href).toBe("/auth/login?redirect=%2Fworkflow%3Ftab%3Drecent"));
  });
});
