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
    expect(mocks.apiFetch).toHaveBeenCalledTimes(3);
    expect(screen.queryByText(/installation-1/)).toBeNull();

    alertAvailable = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(mocks.apiFetch).toHaveBeenCalledTimes(6);
    expect(screen.getByText(/installation-1/)).toBeTruthy();

    view.unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(mocks.apiFetch).toHaveBeenCalledTimes(6);
  });

  it("acknowledges an integrity alert, hides it after refresh, and shows a reopened occurrence", async () => {
    let alertState: "open" | "acknowledged" | "reopened" = "open";
    const alert = (occurrence_count: number) => ({
      id: 41, installation_id: "installation-alert-41", reason: "modified_file",
      component: "api/app.py", expected_sha256: "a".repeat(64),
      observed_sha256: "b".repeat(64), first_seen_at: "2026-10-26T00:00:00Z",
      last_seen_at: "2026-10-26T00:00:00Z", occurrence_count,
    });
    mocks.apiFetch.mockImplementation((endpoint: string, options?: { method?: string }) => {
      if (endpoint.endsWith("/alerts/41/acknowledge") && options?.method === "POST") {
        alertState = "acknowledged";
        return Promise.resolve({ acknowledged: true });
      }
      if (endpoint.endsWith("/alerts")) {
        if (alertState === "open") return Promise.resolve([alert(1)]);
        if (alertState === "reopened") return Promise.resolve([alert(2)]);
        return Promise.resolve([]);
      }
      return Promise.resolve([]);
    });

    render(<ClientInstallationsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText(/1 check/)).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mocks.apiFetch).toHaveBeenCalledWith(
      "/admin/client-installations/alerts/41/acknowledge", { method: "POST" },
    );
    expect(screen.queryByText(/installation-alert-41/)).toBeNull();

    alertState = "reopened";
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(screen.getByText(/installation-alert-41/)).toBeTruthy();
    expect(screen.getByText(/2 checks/)).toBeTruthy();
  });

  it("verifies requested domains before owner approval and displays the replacement token once", async () => {
    mocks.apiFetch.mockImplementation((endpoint: string, options?: { method?: string }) => {
      if (endpoint.includes("/binding-requests") && !options?.method) {
        return Promise.resolve([{
          id: 23,
          installation_id: "client-23",
          customer_id: "customer-23",
          requested_domains: ["voice.new-customer.example"],
          requested_ip_ranges: ["198.51.100.10/32"],
          reason: "Moving servers",
          status: "pending",
          created_at: "2026-10-29T10:00:00Z",
        }]);
      }
      if (endpoint.endsWith("/domain-challenges") && options?.method === "POST") {
        return Promise.resolve({
          customer_id: "customer-23",
          domain: "voice.new-customer.example",
          record_name: "_kodewaves-verification.voice.new-customer.example",
          record_type: "TXT",
          record_value: "kodewaves-verification=challenge",
          expires_at: 1_900_000_000,
        });
      }
      if (endpoint.endsWith("/binding-requests/23/approve") && options?.method === "POST") {
        return Promise.resolve({
          installation_id: "client-23",
          token: "replacement-license-token",
          public_key: "owner-public-key",
          expires_at: 1_900_000_000,
        });
      }
      if (endpoint.endsWith("/alerts")) return Promise.resolve([]);
      return Promise.resolve([]);
    });
    render(<ClientInstallationsPage />);
    await act(async () => { await Promise.resolve(); });

    expect(screen.getByText("Moving servers")).toBeTruthy();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Create DNS challenge · voice.new-customer.example" }));
    });
    expect(screen.getByText("kodewaves-verification=challenge")).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Approve and issue token" }));
    });
    expect(mocks.apiFetch).toHaveBeenCalledWith(
      "/admin/client-installations/binding-requests/23/approve",
      { method: "POST" },
    );
    expect(screen.getByDisplayValue("replacement-license-token")).toBeTruthy();
  });

  it("lets an owner recover the exact token from an approved binding request", async () => {
    mocks.apiFetch.mockImplementation((endpoint: string, options?: { method?: string }) => {
      if (endpoint.includes("/binding-requests") && !options?.method) return Promise.resolve([{
        id: 24,
        installation_id: "client-24",
        customer_id: "customer-24",
        requested_domains: ["voice.customer.example"],
        requested_ip_ranges: [],
        reason: "Approval response was lost",
        status: "approved",
        created_at: "2026-10-29T10:00:00Z",
      }]);
      if (endpoint.endsWith("/binding-requests/24/recover-token") && options?.method === "POST") {
        return Promise.resolve({
          installation_id: "client-24",
          token: "recovered-license-token",
          public_key: "owner-public-key",
          expires_at: 1_900_000_000,
          recovered: true,
        });
      }
      return Promise.resolve([]);
    });

    render(<ClientInstallationsPage />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText(/approved ·/)).toBeTruthy();
    expect(screen.queryByDisplayValue("recovered-license-token")).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Recover approved license" }));
    });
    expect(screen.getByDisplayValue("recovered-license-token")).toBeTruthy();
    expect(mocks.apiFetch).toHaveBeenCalledWith(
      "/admin/client-installations/binding-requests/24/recover-token",
      { method: "POST" },
    );
  });

  it("surfaces the installation trust boundary and all owner actions in the registry card", async () => {
    mocks.apiFetch.mockImplementation((endpoint: string) => Promise.resolve(
      endpoint.endsWith("/alerts") || endpoint.includes("/binding-requests") ? [] : [{
        installation_id: "customer-prod-eu", customer_id: "customer-42",
        domains: ["voice.customer.example"], ip_ranges: ["198.51.100.10/32"],
        features: ["voice", "crm"], limits: { max_concurrent_calls: 6, max_agents: 20 },
        expires_at: 1_900_000_000, token_fingerprint: "metadata-fingerprint",
        revoked_at: null, last_seen_at: null, observed_ip: "198.51.100.10",
        integrity_failed_at: null, identity_enrolled: false,
      }],
    ));

    render(<ClientInstallationsPage />);
    await act(async () => { await Promise.resolve(); });

    expect(screen.getByText("License active")).toBeTruthy();
    expect(screen.getByText("Identity not enrolled")).toBeTruthy();
    expect(screen.getByText("voice.customer.example")).toBeTruthy();
    expect(screen.getByText("198.51.100.10/32")).toBeTruthy();
    expect(screen.getByText("No client check received")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Create enrollment token" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Renew for 30 days" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Mark revoked" })).toBeTruthy();
    expect(screen.queryByDisplayValue("metadata-fingerprint")).toBeNull();
  });

  it("explains safe recovery and disables renewal after an integrity failure", async () => {
    mocks.apiFetch.mockImplementation((endpoint: string) => Promise.resolve(
      endpoint.endsWith("/alerts") || endpoint.includes("/binding-requests") ? [] : [{
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
      if (endpoint.includes("/binding-requests")) return Promise.resolve([]);
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

  it("renews an installation and displays the replacement token once", async () => {
    const expiresAt = 1_900_000_000;
    const installation = {
      installation_id: "client-1", customer_id: "customer-1", domains: ["customer.example"],
      ip_ranges: [], features: ["voice"], limits: { max_concurrent_calls: 1 },
      expires_at: expiresAt, token_fingerprint: "old-fingerprint", revoked_at: null,
      last_seen_at: null, integrity_failed_at: null,
    };
    mocks.apiFetch.mockImplementation((endpoint: string) => {
      if (endpoint.endsWith("/alerts")) return Promise.resolve([]);
      if (endpoint.includes("/binding-requests")) return Promise.resolve([]);
      if (endpoint.endsWith("/renew")) {
        return Promise.resolve({
          installation_id: "client-1", token: "replacement-token", public_key: "verification-key",
          expires_at: expiresAt + 30 * 86400,
        });
      }
      return Promise.resolve([installation]);
    });
    render(<ClientInstallationsPage />);
    await act(async () => { await Promise.resolve(); });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Renew for 30 days" }));
    });

    expect(mocks.apiFetch).toHaveBeenCalledWith(
      "/admin/client-installations/client-1/renew",
      { method: "POST", body: JSON.stringify({ expires_at: expiresAt + 30 * 86400 }) },
    );
    expect(screen.getByDisplayValue("replacement-token")).toBeTruthy();
  });

  it("confirms revocation, persists it, and refreshes the owner record", async () => {
    const confirmation = vi.spyOn(window, "confirm").mockReturnValue(true);
    let revoked = false;
    const record = {
      installation_id: "client-1", customer_id: "customer-1", domains: ["customer.example"],
      ip_ranges: [], features: ["voice"], limits: { max_concurrent_calls: 1 },
      expires_at: 1_900_000_000, token_fingerprint: "fingerprint",
      revoked_at: null as string | null, last_seen_at: null, integrity_failed_at: null,
    };
    mocks.apiFetch.mockImplementation((endpoint: string, options?: { method?: string }) => {
      if (endpoint.endsWith("/alerts")) return Promise.resolve([]);
      if (endpoint.includes("/binding-requests")) return Promise.resolve([]);
      if (endpoint.endsWith("/revoke") && options?.method === "POST") {
        revoked = true;
        record.revoked_at = "2026-10-28T00:00:00Z";
        return Promise.resolve({ installation_id: "client-1", revoked_at: record.revoked_at });
      }
      return Promise.resolve([{ ...record, revoked_at: revoked ? record.revoked_at : null }]);
    });
    render(<ClientInstallationsPage />);
    await act(async () => { await Promise.resolve(); });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Mark revoked" }));
    });

    expect(confirmation).toHaveBeenCalledWith(expect.stringContaining("Mark installation client-1 revoked?"));
    expect(mocks.apiFetch).toHaveBeenCalledWith(
      "/admin/client-installations/client-1/revoke", { method: "POST" },
    );
    expect(screen.getByText(/Marked revoked/)).toBeTruthy();
  });
});
