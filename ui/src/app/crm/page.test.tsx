import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  auth: { loading: true, user: null as null | { id: string } },
  getContacts: vi.fn(),
  getStages: vi.fn(),
  createContact: vi.fn(),
  updateContact: vi.fn(),
  deleteContact: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => mocks.auth }));
vi.mock("@/lib/kodewavesApi", () => ({ crmApi: mocks }));
import CRMPage from "./page";

const firstStage = { id: "11111111-1111-4111-8111-111111111111", name: "New Lead" };
const selectedStage = { id: "22222222-2222-4222-8222-222222222222", name: "Qualified" };

beforeEach(() => {
  mocks.auth = { loading: true, user: null };
  for (const mock of [mocks.getContacts, mocks.getStages, mocks.createContact, mocks.updateContact, mocks.deleteContact]) {
    mock.mockReset();
  }
  mocks.getContacts.mockResolvedValue([]);
  mocks.getStages.mockResolvedValue([firstStage, selectedStage]);
  mocks.createContact.mockResolvedValue({});
  mocks.updateContact.mockResolvedValue({});
  mocks.deleteContact.mockResolvedValue({});
  HTMLElement.prototype.scrollIntoView = vi.fn();
});

describe("CRM page loading", () => {
  it("waits for authentication, then tolerates contacts without a first name", async () => {
    mocks.getContacts.mockResolvedValue([{ id: "contact-1", first_name: null, phone: "+15550123456" }]);
    mocks.getStages.mockResolvedValue([]);
    const view = render(<CRMPage />);
    expect(mocks.getContacts).not.toHaveBeenCalled();
    mocks.auth = { loading: false, user: { id: "user-1" } };
    view.rerender(<CRMPage />);
    expect((await screen.findAllByText("+15550123456")).length).toBeGreaterThan(0);
    expect(mocks.getContacts).toHaveBeenCalledTimes(1);
  });

  it("shows a failed load instead of silently replacing server data", async () => {
    mocks.auth = { loading: false, user: { id: "user-1" } };
    mocks.getContacts.mockRejectedValue(new Error("CRM unavailable"));
    mocks.getStages.mockResolvedValue([]);
    render(<CRMPage />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("CRM unavailable"));
  });
});

describe("CRM lead-stage editing", () => {
  it("preserves the UUID stage selected when creating a contact", async () => {
    mocks.auth = { loading: false, user: { id: "user-1" } };
    render(<CRMPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Add a lead" }));
    fireEvent.change(screen.getByPlaceholderText("Rahul"), { target: { value: "Asha" } });
    fireEvent.change(screen.getByPlaceholderText("+91 98765 43210"), { target: { value: "+919876543210" } });
    const selects = screen.getAllByRole("combobox");
    fireEvent.click(selects[selects.length - 1]);
    fireEvent.click(await screen.findByRole("option", { name: "Qualified" }));
    fireEvent.click(screen.getByRole("button", { name: "Save contact" }));

    await waitFor(() => expect(mocks.createContact).toHaveBeenCalledWith(expect.objectContaining({
      first_name: "Asha",
      phone: "+919876543210",
      stage_id: selectedStage.id,
    })));
  });

  it("shows stage counts and filters both the records view and its result count", async () => {
    mocks.auth = { loading: false, user: { id: "user-1" } };
    mocks.getContacts.mockResolvedValue([
      { id: "contact-1", first_name: "Asha", last_name: "Rao", phone: "+919876543210", stage_id: firstStage.id },
      { id: "contact-2", first_name: "Kabir", last_name: "Shah", phone: "+919876543211", stage_id: selectedStage.id },
    ]);
    render(<CRMPage />);

    expect(await screen.findByRole("button", { name: /All contacts/ })).toBeTruthy();
    const qualifiedStage = screen.getByRole("button", { name: /Qualified/ });
    expect(qualifiedStage.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(qualifiedStage);

    await waitFor(() => expect(qualifiedStage.getAttribute("aria-pressed")).toBe("true"));
    expect(screen.getAllByText("Kabir Shah").length).toBeGreaterThan(0);
    expect(screen.queryByText("Asha Rao")).toBeNull();
    expect(screen.getByText("Showing Qualified leads")).toBeTruthy();
  });

  it("shows a useful empty state and clears search and stage filters", async () => {
    mocks.auth = { loading: false, user: { id: "user-1" } };
    mocks.getContacts.mockResolvedValue([
      { id: "contact-1", first_name: "Asha", last_name: "Rao", phone: "+919876543210", stage_id: firstStage.id },
    ]);
    render(<CRMPage />);

    const search = await screen.findByRole("textbox", { name: "Search contacts" });
    fireEvent.change(search, { target: { value: "no-match" } });
    expect(await screen.findByRole("heading", { name: "No contacts match this view" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findAllByText("Asha Rao")).not.toHaveLength(0);
  });
});
