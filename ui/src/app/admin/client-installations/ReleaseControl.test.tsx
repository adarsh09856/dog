import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  auth: { loading: false, user: { id: 1, is_superuser: true } as null | { id: number; is_superuser: boolean } },
  apiFetch: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => mocks.auth }));
vi.mock("@/lib/kodewavesApi", () => ({ apiFetch: mocks.apiFetch }));

import { ClientReleaseControl } from "./ReleaseControl";

const installation = {
  installation_id: "client-install-01",
  customer_id: "Acme",
  identity_enrolled: true,
  expires_at: Math.floor(Date.now() / 1000) + 86400,
  revoked_at: null,
  integrity_failed_at: null,
};

const envelope = {
  release_id: "kodewaves-1.48.0",
  version: "1.48.0",
  archive_url: "https://downloads.example.com/client-1.48.0.tar.gz",
  archive_sha256: "a".repeat(64),
  archive_signature: "A".repeat(86),
  min_current_version: "1.47.0",
  notes: "Maintenance release",
};

describe("owner client release controls", () => {
  beforeEach(() => {
    mocks.auth = { loading: false, user: { id: 1, is_superuser: true } };
    mocks.apiFetch.mockReset().mockImplementation(async (endpoint: string) => {
      if (endpoint.endsWith("/releases")) return [];
      if (endpoint.endsWith("/rollouts")) return [];
      return {};
    });
    vi.stubGlobal("confirm", vi.fn(() => true));
  });

  it("creates and publishes a signed release, stages a rollout, then activates it", async () => {
    const releases: Array<Record<string, unknown>> = [];
    const rollouts: Array<Record<string, unknown>> = [];
    mocks.apiFetch.mockImplementation(async (endpoint: string, options?: RequestInit) => {
      if (endpoint.endsWith("/releases") && !options?.method) return [...releases];
      if (endpoint.endsWith("/rollouts") && !options?.method) return [...rollouts];
      if (endpoint.endsWith("/releases") && options?.method === "POST") {
        const parsed = JSON.parse(String(options.body));
        const release = { ...parsed, state: "draft", created_at: "2026-11-03T10:00:00Z", published_at: null };
        releases.push(release);
        return release;
      }
      if (endpoint.endsWith("/publish")) {
        releases[0].state = "published";
        return releases[0];
      }
      if (endpoint.endsWith("/rollouts") && options?.method === "POST") {
        const parsed = JSON.parse(String(options.body));
        const rollout = {
          rollout_id: "rollout-123456",
          release_id: parsed.release_id,
          state: "staged",
          targets: parsed.installation_ids.map((installation_id: string) => ({ installation_id, status: "staged" })),
        };
        rollouts.push(rollout);
        return { ...rollout, created: true };
      }
      if (endpoint.endsWith("/activate")) {
        rollouts[0].state = "active";
        return rollouts[0];
      }
      return {};
    });

    render(<ClientReleaseControl installations={[installation]} />);
    fireEvent.click(screen.getByRole("button", { name: "Manage releases and rollouts" }));
    await screen.findByText("No signed releases have been added.");

    fireEvent.change(screen.getByLabelText("Signed release envelope JSON"), {
      target: { value: JSON.stringify(envelope) },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save release draft" }));
    expect(await screen.findByText(/saved as a draft/)).toBeTruthy();
    expect(mocks.apiFetch).toHaveBeenCalledWith("/admin/client-installations/releases", expect.objectContaining({
      method: "POST",
      body: JSON.stringify(envelope),
    }));
    expect(screen.getByRole("heading", { name: "v1.48.0" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Review and publish" }));
    await waitFor(() => expect(releases[0].state).toBe("published"));
    expect(await screen.findByText(/is published and available/)).toBeTruthy();

    fireEvent.click(screen.getByLabelText(/Acme/));
    fireEvent.click(screen.getByRole("button", { name: "Stage rollout for 1" }));
    expect(await screen.findByText(/Activate it when ready/)).toBeTruthy();
    const createCall = mocks.apiFetch.mock.calls.find(([path, options]) => path.endsWith("/rollouts") && options?.method === "POST");
    expect(createCall?.[1].headers).toEqual({ "Idempotency-Key": expect.stringMatching(/^[A-Za-z0-9._:-]{16,100}$/) });

    fireEvent.click(screen.getByRole("button", { name: "Activate" }));
    await waitFor(() => expect(rollouts[0].state).toBe("active"));
    expect(await screen.findByText(/Rollout rollout-123456 activated/)).toBeTruthy();
  });

  it("rejects private key material and never sends it to the API", async () => {
    render(<ClientReleaseControl installations={[installation]} />);
    fireEvent.click(screen.getByRole("button", { name: "Manage releases and rollouts" }));
    await screen.findByText("No signed releases have been added.");

    fireEvent.change(screen.getByLabelText("Signed release envelope JSON"), {
      target: { value: JSON.stringify({ ...envelope, private_key: "must-not-leave-browser" }) },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save release draft" }));

    expect((await screen.findByRole("alert")).textContent).toMatch(/must contain only/);
    expect(mocks.apiFetch).not.toHaveBeenCalledWith("/admin/client-installations/releases", expect.objectContaining({ method: "POST" }));
  });

  it("does not issue owner release requests for a non-owner", async () => {
    mocks.auth = { loading: false, user: { id: 2, is_superuser: false } };
    const view = render(<ClientReleaseControl installations={[installation]} />);
    await act(async () => { await Promise.resolve(); });
    expect(view.container.textContent).toBe("");
    expect(mocks.apiFetch).not.toHaveBeenCalled();
  });

  it("surfaces an unexpected rollout payload instead of crashing the owner page", async () => {
    mocks.apiFetch.mockImplementation(async (endpoint: string) => {
      if (endpoint.endsWith("/releases")) return [];
      if (endpoint.endsWith("/rollouts")) return [{ rollout_id: "rollout-missing-targets" }];
      return [];
    });

    render(<ClientReleaseControl installations={[installation]} />);
    fireEvent.click(screen.getByRole("button", { name: "Manage releases and rollouts" }));

    expect((await screen.findByRole("alert")).textContent).toMatch(/unexpected rollout response/i);
  });
});
