import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  auth: { user: { id: "user" } as { id: string } | null, loading: false },
  getContacts: vi.fn(),
  getStages: vi.fn(),
  createContact: vi.fn(),
  updateContact: vi.fn(),
  deleteContact: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => mocks.auth }));
vi.mock("@/lib/kodewavesApi", () => ({
  crmApi: {
    getContacts: mocks.getContacts,
    getStages: mocks.getStages,
    createContact: mocks.createContact,
    updateContact: mocks.updateContact,
    deleteContact: mocks.deleteContact,
  },
}));

import CRMPage from "./page";

const firstStage = { id: "11111111-1111-4111-8111-111111111111", name: "New Lead" };
const selectedStage = { id: "22222222-2222-4222-8222-222222222222", name: "Qualified" };

beforeEach(() => {
  vi.clearAllMocks();
  HTMLElement.prototype.scrollIntoView = vi.fn();
  mocks.auth.user = { id: "user" };
  mocks.getContacts.mockResolvedValue([]);
  mocks.getStages.mockResolvedValue([firstStage, selectedStage]);
  mocks.createContact.mockResolvedValue({});
  mocks.updateContact.mockResolvedValue({});
  mocks.deleteContact.mockResolvedValue({});
});

describe("CRM lead-stage editing", () => {
  it("preserves the UUID stage selected when creating a contact", async () => {
    render(<CRMPage />);

    fireEvent.click(await screen.findByRole("button", { name: /add lead/i }));
    fireEvent.change(screen.getByPlaceholderText("Rahul"), { target: { value: "Asha" } });
    fireEvent.change(screen.getByPlaceholderText("+91 98765 43210"), { target: { value: "+919876543210" } });
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(await screen.findByRole("option", { name: "Qualified" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Lead" }));

    await waitFor(() => expect(mocks.createContact).toHaveBeenCalledWith(expect.objectContaining({
      first_name: "Asha",
      phone: "+919876543210",
      stage_id: selectedStage.id,
    })));
  });
});
