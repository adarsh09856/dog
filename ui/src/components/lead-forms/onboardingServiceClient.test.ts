import { afterEach, describe, expect, it, vi } from "vitest";

describe("public lead service configuration", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("does not claim a lead was accepted when the service URL is not configured", async () => {
    vi.stubEnv("NEXT_PUBLIC_ONBOARDING_API_URL", "");
    vi.resetModules();
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const { postLeadToService } = await import("./onboardingServiceClient");

    await expect(postLeadToService("enterprise", { workEmail: "buyer@example.com" })).resolves.toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
