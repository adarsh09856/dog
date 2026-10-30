import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ auth: { user: { id: "user-1", organizationId: 7 }, loading: false }, redirect: vi.fn() }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ ...mocks.auth, redirectToLogin: mocks.redirect }) }));
vi.mock("./DocumentList", () => ({ default: ({ refreshTrigger }: { refreshTrigger: number }) => <div data-testid="document-list" data-refresh={refreshTrigger}>Documents {refreshTrigger}</div> }));
vi.mock("./DocumentUpload", () => ({ default: ({ onUploadSuccess }: { onUploadSuccess: () => void }) => <button onClick={onUploadSuccess}>Finish upload</button> }));

import Page from "./page";

beforeEach(() => {
  mocks.auth = { user: { id: "user-1", organizationId: 7 }, loading: false };
  mocks.redirect.mockReset();
});
afterEach(cleanup);

it("opens the upload flow and refreshes the organization document list after success", async () => {
  render(<Page />);
  expect(screen.getByRole("heading", { name: "Knowledge base" })).toBeTruthy();
  expect(screen.getByTestId("document-list").getAttribute("data-refresh")).toBe("0");
  fireEvent.click(screen.getByRole("button", { name: "Upload files" }));
  fireEvent.click(await screen.findByRole("button", { name: "Finish upload" }));
  expect(screen.queryByRole("button", { name: "Finish upload" })).toBeNull();
  expect(screen.getByTestId("document-list").getAttribute("data-refresh")).toBe("1");
});
