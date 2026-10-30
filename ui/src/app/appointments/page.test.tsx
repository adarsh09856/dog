import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  auth: { user: { id: "user-1" }, loading: false },
  getAppointments: vi.fn(), createAppointment: vi.fn(), updateAppointment: vi.fn(), deleteAppointment: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => mocks.auth }));
vi.mock("@/context/OrgConfigContext", () => ({ useOrgConfig: () => ({ organizationPreferences: { timezone: "Asia/Kolkata" }, loading: false }) }));
vi.mock("@/lib/kodewavesApi", () => ({ appointmentsApi: mocks, __esModule: true }));
vi.mock("@/components/SavedContactSelector", () => ({ SavedContactSelector: () => <div>Saved contacts</div> }));

import Page from "./page";

const appointments = [
  { id: 1, title: "Product demo", customer_name: "Asha Rao", customer_phone: "+919876543210", customer_email: "asha@example.com", start_time: "2027-01-10T10:00:00+05:30", end_time: "2027-01-10T10:30:00+05:30", status: "confirmed", notes: "Interested in onboarding" },
  { id: 2, title: "Callback", customer_name: "Kabir Shah", customer_phone: "+919876543211", customer_email: "", start_time: "2027-01-11T11:00:00+05:30", end_time: "2027-01-11T11:30:00+05:30", status: "pending", notes: "" },
];

beforeEach(() => {
  mocks.auth = { user: { id: "user-1" }, loading: false };
  HTMLElement.prototype.scrollIntoView = vi.fn();
  mocks.getAppointments.mockReset().mockResolvedValue(appointments);
  mocks.createAppointment.mockReset().mockResolvedValue({});
  mocks.updateAppointment.mockReset().mockResolvedValue({});
  mocks.deleteAppointment.mockReset().mockResolvedValue({});
});
afterEach(cleanup);

describe("Appointments workspace", () => {
  it("loads bookings and filters cards by customer or meeting text", async () => {
    render(<Page />);
    expect((await screen.findAllByText("Asha Rao")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Kabir Shah").length).toBeGreaterThan(0);

    fireEvent.change(screen.getByRole("textbox", { name: "Search appointments" }), { target: { value: "asha" } });
    expect(screen.getAllByText("Asha Rao").length).toBeGreaterThan(0);
    expect(screen.queryByText("Kabir Shah")).toBeNull();

    fireEvent.change(screen.getByRole("textbox", { name: "Search appointments" }), { target: { value: "" } });
    fireEvent.click(screen.getByRole("combobox", { name: "Filter appointments by status" }));
    fireEvent.click(await screen.findByRole("option", { name: "Pending" }));
    expect(screen.queryByText("Asha Rao")).toBeNull();
    expect(screen.getAllByText("Kabir Shah").length).toBeGreaterThan(0);
  });

  it("keeps edit available from the compact booking card", async () => {
    render(<Page />);
    await screen.findAllByText("Asha Rao");
    fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[0]);
    expect(await screen.findByText("Edit Appointment")).toBeTruthy();
    expect(screen.getByDisplayValue("Asha Rao")).toBeTruthy();
  });

  it("surfaces load failures with a retry action", async () => {
    mocks.getAppointments.mockRejectedValueOnce(new Error("Appointments unavailable"));
    render(<Page />);
    expect((await screen.findByRole("alert")).textContent).toContain("Appointments unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(mocks.getAppointments).toHaveBeenCalledTimes(2));
    expect((await screen.findAllByText("Asha Rao")).length).toBeGreaterThan(0);
  });
});
