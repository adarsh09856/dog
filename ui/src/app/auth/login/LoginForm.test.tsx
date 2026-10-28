import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/client/sdk.gen", () => ({ loginApiV1AuthLoginPost: vi.fn() }));
vi.mock("@/components/auth/AuthEnterpriseCTA", () => ({ AuthEnterpriseCTA: () => null }));
vi.mock("@/components/auth/AuthShell", () => ({
  AuthShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { LoginForm } from "./LoginForm";

describe("LoginForm pricing continuation", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/auth/login");
  });

  it("keeps a selected plan and period when a visitor chooses sign up", async () => {
    window.history.replaceState({}, "", "/auth/login?plan=pro&billing_cycle=annual");
    render(<LoginForm signupEnabled />);

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Sign up" }).getAttribute("href"))
        .toBe("/auth/signup?plan=pro&billing_cycle=annual");
    });
  });

  it("keeps a selected credit package when a visitor chooses sign up", async () => {
    window.history.replaceState({}, "", "/auth/login?credit_package=minutes-500");
    render(<LoginForm signupEnabled />);

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Sign up" }).getAttribute("href"))
        .toBe("/auth/signup?credit_package=minutes-500");
    });
  });
});
