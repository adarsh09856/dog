import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ auth: { user: { id: "user-1", organizationId: 7 }, loading: false }, redirect: vi.fn() }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ ...mocks.auth, redirectToLogin: mocks.redirect }) }));
vi.mock("./RecordingsList", () => ({ default: ({ refreshKey }: { refreshKey: number }) => <div data-testid="recordings-list" data-refresh={refreshKey}>Source recordings</div> }));
vi.mock("./TtsCacheList", () => ({ default: () => <div>Generated speech cache</div> }));
vi.mock("./RecordingsUploadDialog", () => ({ RecordingsUploadDialog: ({ open, onUploadComplete }: { open: boolean; onUploadComplete: () => void }) => open ? <div role="dialog"><button onClick={onUploadComplete}>Complete upload</button></div> : null }));

import Page from "./page";

beforeEach(() => {
  mocks.auth = { user: { id: "user-1", organizationId: 7 }, loading: false };
  mocks.redirect.mockReset();
});
afterEach(cleanup);

it("switches between source and generated audio libraries and refreshes recordings after upload", async () => {
  render(<Page />);
  expect(screen.getByRole("heading", { name: "Audio library" })).toBeTruthy();
  expect(screen.getByTestId("recordings-list").getAttribute("data-refresh")).toBe("0");
  fireEvent.mouseDown(screen.getByRole("tab", { name: "TTS cache" }), { button: 0 });
  expect(await screen.findByText("Generated speech cache")).toBeTruthy();
  fireEvent.mouseDown(screen.getByRole("tab", { name: "Uploaded recordings" }), { button: 0 });
  fireEvent.click(screen.getByRole("button", { name: "Upload recording" }));
  fireEvent.click(await screen.findByRole("button", { name: "Complete upload" }));
  expect(screen.getByTestId("recordings-list").getAttribute("data-refresh")).toBe("1");
});
