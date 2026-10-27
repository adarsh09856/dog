import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ apiFetch: vi.fn(), user: { id: 1 } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: mocks.user, loading: false }) }));
vi.mock("@/lib/kodewavesApi", () => ({ apiFetch: mocks.apiFetch }));

afterEach(() => { cleanup(); vi.unstubAllEnvs(); vi.resetModules(); mocks.apiFetch.mockReset(); });

describe("client entitlement refresh", () => {
  it("keeps the newest denial when an older valid response arrives late", async () => {
    vi.stubEnv("NEXT_PUBLIC_KODEWAVES_EDITION", "client");
    let resolveOld!: (value: unknown) => void;
    mocks.apiFetch.mockReturnValueOnce(new Promise((resolve) => { resolveOld = resolve; }))
      .mockResolvedValueOnce({ valid: false, features: [], limits: {}, message: "License revoked" });
    const { ClientEntitlementsProvider, useClientEntitlements } = await import("./ClientEntitlementsContext");
    function View() {
      const access = useClientEntitlements();
      return <><span>{access.message || "no error"}</span><span>{access.hasFeature("voice") ? "allowed" : "denied"}</span><button onClick={() => void access.refresh()}>Refresh</button></>;
    }
    render(<ClientEntitlementsProvider><View /></ClientEntitlementsProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(screen.getByText("License revoked")).toBeTruthy());
    await act(async () => resolveOld({ valid: true, features: ["voice"], limits: {} }));
    expect(screen.getByText("License revoked")).toBeTruthy();
    expect(screen.getByText("denied")).toBeTruthy();
  });
});
