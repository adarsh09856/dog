import { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/deploymentEdition", () => ({
  isHiddenInClientEdition: () => false,
}));

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

  it("still redirects protected workspace pages to sign-in without a session", async () => {
    const response = await middleware(new NextRequest("http://localhost/workflow"));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost/auth/login?redirect=%2Fworkflow");
  });
});
