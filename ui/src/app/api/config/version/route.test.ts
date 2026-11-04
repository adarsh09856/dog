// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.fn();
vi.mock("@/lib/apiClient", () => ({
  getServerBackendUrl: () => "http://api:8000",
}));

import { GET } from "./route";

describe("GET /api/config/version", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(
      Response.json({
        version: "api-test",
        deployment_mode: "saas",
        auth_provider: "local",
        turn_enabled: false,
        force_turn_relay: false,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("BACKEND_URL", "http://api:8000");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("exposes the full source commit SHA embedded in the UI image", async () => {
    const commitSha = "a".repeat(40);
    vi.stubEnv("KODEWAVES_BUILD_SHA", commitSha);

    const response = await GET();
    const body = await response.json();

    expect(body.ui_build_sha).toBe(commitSha);
  });

  it("uses the local dev fallback when no build SHA was supplied", async () => {
    vi.stubEnv("KODEWAVES_BUILD_SHA", "");

    const response = await GET();
    const body = await response.json();

    expect(body.ui_build_sha).toBe("dev");
  });
});
