import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  list: vi.fn(), create: vi.fn(), archive: vi.fn(), unarchive: vi.fn(), workflows: vi.fn(),
  token: vi.fn().mockResolvedValue("synthetic"), user: { id: 1 }, push: vi.fn(), login: vi.fn(),
}));

vi.mock("@/client/sdk.gen", () => ({
  listToolsApiV1ToolsGet: mocks.list,
  createToolApiV1ToolsPost: mocks.create,
  deleteToolApiV1ToolsToolUuidDelete: mocks.archive,
  getWorkflowsSummaryApiV1WorkflowSummaryGet: mocks.workflows,
  unarchiveToolApiV1ToolsToolUuidUnarchivePost: mocks.unarchive,
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: mocks.user, loading: false, getAccessToken: mocks.token, redirectToLogin: mocks.login }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("@/components/http", () => ({ CredentialSelector: () => null }));

import Page from "./page";

const activeTool = {
  id: 1, tool_uuid: "tool-1", name: "Inventory lookup", category: "http_api", status: "active",
  description: "Look up current stock levels", icon: "globe", icon_color: "#3B82F6", definition: {},
};

beforeEach(() => {
  mocks.list.mockReset().mockResolvedValue({ data: [activeTool] });
  mocks.create.mockReset().mockResolvedValue({ data: { tool_uuid: "tool-2" } });
  mocks.archive.mockReset().mockResolvedValue({ data: { message: "archived" } });
  mocks.unarchive.mockReset().mockResolvedValue({ data: { message: "restored" } });
  mocks.workflows.mockReset().mockResolvedValue({ data: [] });
  mocks.token.mockReset().mockResolvedValue("synthetic");
  mocks.push.mockReset();
  mocks.login.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Tools collection", () => {
  it("shows a load failure instead of an empty collection and allows retry", async () => {
    mocks.list.mockResolvedValueOnce({ error: { detail: "Tools unavailable" } }).mockResolvedValue({ data: [] });
    render(<Page />);
    expect((await screen.findByRole("alert")).textContent).toContain("Tools unavailable");
    expect(screen.queryByText("No tools found")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No tools found")).toBeTruthy();
  });

  it("filters tools by search and opens the selected tool detail route", async () => {
    render(<Page />);
    expect(await screen.findByText("Inventory lookup")).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Search tools" }), { target: { value: "nothing" } });
    expect(screen.getByText("No tools match your search")).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Search tools" }), { target: { value: "stock" } });
    fireEvent.click(screen.getByText("Inventory lookup"));
    expect(mocks.push).toHaveBeenCalledWith("/tools/tool-1");
  });

  it("preserves the archive confirmation and isolates the row action from navigation", async () => {
    const confirmMock = vi.fn().mockReturnValue(true);
    vi.stubGlobal("confirm", confirmMock);
    render(<Page />);
    await screen.findByText("Inventory lookup");
    fireEvent.click(screen.getByRole("button", { name: "Archive Inventory lookup" }));
    await waitFor(() => expect(mocks.archive).toHaveBeenCalledWith({
      path: { tool_uuid: "tool-1" }, headers: { Authorization: "Bearer synthetic" },
    }));
    expect(confirmMock).toHaveBeenCalledWith("Are you sure you want to archive this tool?");
    expect(mocks.push).not.toHaveBeenCalled();
  });
});
