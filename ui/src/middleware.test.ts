import { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";

import { middleware } from "./middleware";

describe("public route access", () => {
  it.each(["/", "/pricing", "/platform", "/deployment"]) (
    "%s is available without a workspace session",
    async (pathname) => {
      const response = await middleware(new NextRequest(`http://localhost${pathname}`));
      expect(response.status).toBe(200);
      expect(response.headers.get("x-middleware-next")).toBe("1");
    },
  );

  it.each(["/billing", "/billing-sovereign", "/superadmin/client-installations"]) (
    "hides hosted billing and owner routes in a client installation: %s",
    async (pathname) => {
      vi.stubEnv("KODEWAVES_EDITION", "client");
      try {
        const response = await middleware(new NextRequest(`http://localhost${pathname}`));
        expect(response.status).toBe(404);
      } finally {
        vi.unstubAllEnvs();
      }
    },
  );

  it("keeps customer workspace administration in a client installation", async () => {
    vi.stubEnv("KODEWAVES_EDITION", "client");
    try {
      const response = await middleware(new NextRequest("http://localhost/admin"));
      expect(response.status).toBe(307);
      expect(response.headers.get("location")).toBe("http://localhost/auth/login?redirect=%2Fadmin");
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it("still redirects protected workspace pages to sign-in without a session", async () => {
    const response = await middleware(new NextRequest("http://localhost/workflow"));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost/auth/login?redirect=%2Fworkflow");
  });
});
