import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getBannedWords: vi.fn(),
  getViolations: vi.fn(),
  addBannedWord: vi.fn(),
  deleteBannedWord: vi.fn(),
  resolveViolation: vi.fn(),
  deleteViolation: vi.fn(),
}));

vi.mock("@/lib/kodewavesApi", () => ({ adminApi: mocks }));

import AdminModerationPage from "./page";

describe("admin moderation data loading", () => {
  beforeEach(() => {
    mocks.getBannedWords.mockReset().mockResolvedValue([]);
    mocks.getViolations.mockReset().mockResolvedValue([]);
    mocks.addBannedWord.mockReset().mockResolvedValue({});
    mocks.deleteBannedWord.mockReset().mockResolvedValue({});
    mocks.resolveViolation.mockReset().mockResolvedValue({});
    mocks.deleteViolation.mockReset().mockResolvedValue({});
  });

  it("shows the failed load and prevents edits until a successful retry", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    mocks.getBannedWords
      .mockRejectedValueOnce(new Error("Moderation service unavailable"))
      .mockResolvedValueOnce([]);

    render(<AdminModerationPage />);

    expect((await screen.findByRole("alert")).textContent).toContain("Moderation service unavailable");
    expect(screen.getByRole("button", { name: "Add Banned Keyword" })).toHaveProperty("disabled", true);
    expect(screen.getByText("Moderation data unavailable. Use Refresh to retry.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(await screen.findByText(/No keywords banned/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add Banned Keyword" })).toHaveProperty("disabled", false);
    consoleError.mockRestore();
  });
});
