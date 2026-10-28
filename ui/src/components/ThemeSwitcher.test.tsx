import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  resolvedTheme: "dark" as "light" | "dark",
  setTheme: vi.fn(),
}));

vi.mock("next-themes", () => ({
  useTheme: () => ({ resolvedTheme: mocks.resolvedTheme, setTheme: mocks.setTheme }),
}));

import ThemeToggle from "@/components/ThemeSwitcher";

describe("ThemeToggle", () => {
  beforeEach(() => {
    mocks.resolvedTheme = "dark";
    mocks.setTheme.mockClear();
  });

  it("updates the shared theme state from dark to light", () => {
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole("button", { name: /Toggle theme/ }));

    expect(mocks.setTheme).toHaveBeenCalledWith("light");
  });

  it("updates the shared theme state from light to dark", () => {
    mocks.resolvedTheme = "light";
    render(<ThemeToggle showLabel />);

    fireEvent.click(screen.getByRole("button", { name: /Toggle theme/ }));

    expect(mocks.setTheme).toHaveBeenCalledWith("dark");
  });
});
