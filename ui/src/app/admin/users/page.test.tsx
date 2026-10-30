import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  auth: { loading: true, user: null as null | { id: number; is_superuser: boolean } },
  getUsers: vi.fn(),
  getPlans: vi.fn(),
  updateUser: vi.fn(),
  impersonateUser: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => mocks.auth }));
vi.mock("@/lib/kodewavesApi", () => ({ adminApi: mocks }));

import AdminUsersPage from "./page";

async function passDebounce() {
  await act(async () => { await vi.advanceTimersByTimeAsync(350); });
}

describe("owner user directory loading", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mocks.auth = { loading: true, user: null };
    mocks.getUsers.mockReset().mockResolvedValue([]);
    mocks.getPlans.mockReset().mockResolvedValue([]);
    mocks.updateUser.mockReset().mockResolvedValue({});
  });
  afterEach(() => vi.useRealTimers());

  it("waits for owner authentication and does not fetch for a regular user", async () => {
    const view = render(<AdminUsersPage />);
    await passDebounce();
    expect(mocks.getUsers).not.toHaveBeenCalled();

    mocks.auth = { loading: false, user: { id: 7, is_superuser: false } };
    view.rerender(<AdminUsersPage />);
    await passDebounce();
    expect(mocks.getUsers).not.toHaveBeenCalled();

    mocks.auth = { loading: false, user: { id: 7, is_superuser: true } };
    view.rerender(<AdminUsersPage />);
    await passDebounce();
    expect(mocks.getUsers).toHaveBeenCalledTimes(1);
  });

  it("does not replace a newer filtered result with a slow earlier response", async () => {
    mocks.auth = { loading: false, user: { id: 7, is_superuser: true } };
    let finishEarlier!: (users: unknown[]) => void;
    mocks.getUsers.mockReturnValueOnce(new Promise((resolve) => { finishEarlier = resolve; }));
    mocks.getUsers.mockResolvedValueOnce([]);
    render(<AdminUsersPage />);
    await passDebounce();

    fireEvent.change(screen.getByPlaceholderText("Search by email, name, provider ID..."), {
      target: { value: "newer" },
    });
    await passDebounce();
    expect(mocks.getUsers).toHaveBeenLastCalledWith(expect.objectContaining({ search: "newer" }));

    await act(async () => {
      finishEarlier([{ id: 9, email: "stale@example.com", is_active: true, is_superuser: false }]);
    });
    expect(screen.queryByText("stale@example.com")).toBeNull();
  });

  it("saves only changed fields without rewriting a renamed paid plan or its grants", async () => {
    mocks.auth = { loading: false, user: { id: 7, is_superuser: true } };
    mocks.getUsers.mockResolvedValue([{
      id: 9, email: "customer@example.com", is_active: true, is_superuser: false,
      plan_code: "growth-v2", plan_name: "Renamed Growth Display", max_agents: 12,
    }]);
    mocks.getPlans.mockResolvedValue([{ code: "growth-v2", name: "Renamed Growth Display", is_active: true }]);
    render(<AdminUsersPage />);
    await passDebounce();
    await act(async () => {
      fireEvent.keyDown(screen.getByRole("button", { name: "Manage customer@example.com" }), { key: "Enter" });
    });
    fireEvent.click(screen.getByRole("menuitem", { name: /Edit User & Plan/ }));
    fireEvent.change(screen.getByLabelText("Max Voice Agents"), { target: { value: "0" } });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save Changes" })); });
    expect(mocks.updateUser).toHaveBeenCalledWith(9, { max_agents: 0 });
  });

  it("requires confirmation before starting an impersonation session", async () => {
    mocks.auth = { loading: false, user: { id: 7, is_superuser: true } };
    mocks.getUsers.mockResolvedValue([{ id: 12, email: "tenant@example.com", is_active: true, is_superuser: false }]);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<AdminUsersPage />);
    await passDebounce();
    await act(async () => {
      fireEvent.keyDown(screen.getByRole("button", { name: "Manage tenant@example.com" }), { key: "Enter" });
    });
    fireEvent.click(screen.getByRole("menuitem", { name: /Login As User/ }));
    expect(confirm).toHaveBeenCalledWith("Log in as tenant@example.com and switch to their workspace?");
    expect(mocks.impersonateUser).not.toHaveBeenCalled();
  });

  it("keeps new-account passwords in a masked password field", async () => {
    mocks.auth = { loading: false, user: { id: 7, is_superuser: true } };
    render(<AdminUsersPage />);
    fireEvent.click(screen.getByRole("button", { name: "Create User" }));
    const password = screen.getByPlaceholderText("Minimum 4 characters");
    expect(password.getAttribute("type")).toBe("password");
  });
});
