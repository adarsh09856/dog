import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  auth: { loading: false, user: { id: 7, is_superuser: true } as null | { id: number; is_superuser: boolean } },
  apiFetch: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => mocks.auth }));
vi.mock("@/lib/kodewavesApi", () => ({ apiFetch: mocks.apiFetch }));

import ClientInstallationsPage from "./page";

describe("owner integrity alert refresh", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mocks.auth = { loading: false, user: { id: 7, is_superuser: true } };
    mocks.apiFetch.mockReset().mockResolvedValue([]);
  });

  afterEach(() => vi.useRealTimers());

  it("refreshes owner alert data every 30 seconds and stops polling on unmount", async () => {
    let alertAvailable = false;
    mocks.apiFetch.mockImplementation((endpoint: string) => Promise.resolve(
      endpoint.endsWith("/alerts") && alertAvailable
        ? [{
            id: 1, installation_id: "installation-1", reason: "modified_file",
            component: "api/app.py", expected_sha256: "a".repeat(64),
            observed_sha256: "b".repeat(64), first_seen_at: "2026-10-26T00:00:00Z",
            last_seen_at: "2026-10-26T00:00:00Z", occurrence_count: 1,
          }]
        : [],
    ));
    const view = render(<ClientInstallationsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(mocks.apiFetch).toHaveBeenCalledTimes(2);
    expect(screen.queryByText(/installation-1/)).toBeNull();

    alertAvailable = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(mocks.apiFetch).toHaveBeenCalledTimes(4);
    expect(screen.getByText(/installation-1/)).toBeTruthy();

    view.unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(mocks.apiFetch).toHaveBeenCalledTimes(4);
  });

  it("explains safe recovery and disables renewal after an integrity failure", async () => {
    mocks.apiFetch.mockImplementation((endpoint: string) => Promise.resolve(
      endpoint.endsWith("/alerts") ? [] : [{
        installation_id: "installation-compromised", customer_id: "customer-1",
        domains: ["customer.example"], ip_ranges: [], features: ["voice"],
        limits: { max_concurrent_calls: 1 }, expires_at: 1_800_000_000,
        token_fingerprint: "fingerprint", revoked_at: null, renewed_at: null,
        previous_token_valid_until: null, last_seen_at: null, observed_ip: null,
        integrity_failed_at: "2026-10-26T00:00:00Z",
      }],
    ));
    render(<ClientInstallationsPage />);
    await act(async () => { await Promise.resolve(); });

    expect(screen.getByText(/issue a replacement with a new installation ID/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Renew for 30 days" }).hasAttribute("disabled")).toBe(true);
  });

  it("issues a one-time enrollment token and disables enrollment after key binding", async () => {
    let enrolled = false;
    mocks.apiFetch.mockImplementation((endpoint: string, options?: { method?: string }) => {
      if (endpoint.endsWith("/enrollment-token") && options?.method === "POST") {
        return Promise.resolve({ installation_id: "client-1", enrollment_token: "temporary-secret", expires_at: 1_800_000_000 });
      }
      if (endpoint.endsWith("/alerts")) return Promise.resolve([]);
      return Promise.resolve([{
        installation_id: "client-1", customer_id: "customer-1", domains: ["customer.example"],
        ip_ranges: [], features: ["voice"], limits: { max_concurrent_calls: 1 },
        expires_at: 1_900_000_000, token_fingerprint: "fingerprint", revoked_at: null,
        last_seen_at: null, integrity_failed_at: null, identity_enrolled: enrolled,
      }]);
    });
    render(<ClientInstallationsPage />);
    await act(async () => { await Promise.resolve(); });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Create enrollment token" })); });
    expect(screen.getByDisplayValue("temporary-secret")).toBeTruthy();
    expect(mocks.apiFetch).toHaveBeenCalledWith("/admin/client-installations/client-1/enrollment-token", { method: "POST" });
    enrolled = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(screen.getByText("Installation identity enrolled")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Create enrollment token" }).hasAttribute("disabled")).toBe(true);
  });
});
