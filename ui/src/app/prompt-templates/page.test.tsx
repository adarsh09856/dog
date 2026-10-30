import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  auth: { user: { id: "user" }, loading: false },
  getTemplates: vi.fn(),
  createTemplate: vi.fn(),
  updateTemplate: vi.fn(),
  deleteTemplate: vi.fn(),
  push: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => mocks.auth }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("@/lib/kodewavesApi", () => ({
  promptTemplatesApi: {
    getTemplates: mocks.getTemplates,
    createTemplate: mocks.createTemplate,
    updateTemplate: mocks.updateTemplate,
    deleteTemplate: mocks.deleteTemplate,
  },
}));
vi.mock("@/client/sdk.gen", () => ({ createWorkflowApiV1WorkflowCreateDefinitionPost: vi.fn() }));

import PromptTemplatesPage from "./page";

const systemTemplate = {
  id: "system-1", title: "System template", category: "Healthcare", description: "Shared",
  system_prompt: "System prompt", first_message: "Hello", recommended_tools: [], tags: ["Healthcare"], is_featured: true,
};
const customTemplate = {
  id: "custom-1", title: "Restaurant helper", category: "Hospitality", description: "Custom",
  system_prompt: "Custom prompt", first_message: "Welcome", recommended_tools: [], tags: ["Hospitality"], is_featured: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getTemplates.mockResolvedValue([systemTemplate, customTemplate]);
  mocks.createTemplate.mockResolvedValue({});
  mocks.updateTemplate.mockResolvedValue({});
  mocks.deleteTemplate.mockResolvedValue({});
  vi.stubGlobal("confirm", vi.fn(() => true));
});

describe("prompt template ownership actions", () => {
  it("shows edit/delete only for custom templates and derives filters from loaded categories", async () => {
    render(<PromptTemplatesPage />);

    expect(await screen.findByText("System template")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Edit Restaurant helper" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Delete Restaurant helper" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Edit System template" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete System template" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Real Estate" })).toBeNull();
    expect(screen.getByRole("button", { name: "Hospitality" })).toBeTruthy();
  });

  it("saves edits through the update endpoint and removes a custom template through delete", async () => {
    render(<PromptTemplatesPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Restaurant helper" }));
    fireEvent.change(screen.getByPlaceholderText("e.g. Inbound Restaurant Table Booking"), {
      target: { value: "Updated restaurant helper" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Update Template" }));

    await waitFor(() => expect(mocks.updateTemplate).toHaveBeenCalledWith("custom-1", expect.objectContaining({
      title: "Updated restaurant helper",
      system_prompt: "Custom prompt",
    })));

    fireEvent.click(await screen.findByRole("button", { name: "Delete Restaurant helper" }));
    await waitFor(() => expect(mocks.deleteTemplate).toHaveBeenCalledWith("custom-1"));
    await waitFor(() => expect(screen.queryByText("Restaurant helper")).toBeNull());
  });

  it("returns to all templates when deleting the last template in the active category", async () => {
    render(<PromptTemplatesPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Hospitality" }));
    expect(screen.queryByText("System template")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Delete Restaurant helper" }));

    expect(await screen.findByText("System template")).toBeTruthy();
    expect(screen.getByRole("button", { name: "all" }).className).toContain("bg-primary");
  });
});
