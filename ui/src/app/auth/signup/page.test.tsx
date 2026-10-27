import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { getSignupEnabled, redirect } = vi.hoisted(() => ({
  getSignupEnabled: vi.fn(),
  redirect: vi.fn(() => { throw new Error("NEXT_REDIRECT"); }),
}));

vi.mock("@/lib/auth/config", () => ({ getSignupEnabled }));
vi.mock("next/navigation", () => ({ redirect }));
vi.mock("./SignupForm", () => ({ SignupForm: () => <div>Create an account</div> }));

import SignupPage from "./page";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.clearAllMocks();
});

describe("public signup availability", () => {
  it("redirects client installations before fetching signup configuration", async () => {
    vi.stubEnv("NEXT_PUBLIC_KODEWAVES_EDITION", "client");
    getSignupEnabled.mockResolvedValue(true);

    await expect(SignupPage()).rejects.toThrow("NEXT_REDIRECT");
    expect(redirect).toHaveBeenCalledWith("/auth/login");
    expect(getSignupEnabled).not.toHaveBeenCalled();
  });

  it("redirects hosted instances with public registration disabled", async () => {
    vi.stubEnv("NEXT_PUBLIC_KODEWAVES_EDITION", "saas");
    getSignupEnabled.mockResolvedValue(false);

    await expect(SignupPage()).rejects.toThrow("NEXT_REDIRECT");
    expect(redirect).toHaveBeenCalledWith("/auth/login");
  });

  it("shows registration on a hosted instance that enables it", async () => {
    vi.stubEnv("NEXT_PUBLIC_KODEWAVES_EDITION", "saas");
    getSignupEnabled.mockResolvedValue(true);

    render(await SignupPage());
    expect(screen.getByText("Create an account")).toBeTruthy();
    expect(redirect).not.toHaveBeenCalled();
  });
});
