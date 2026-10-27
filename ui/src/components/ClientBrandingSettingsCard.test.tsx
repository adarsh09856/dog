import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ apiFetch: vi.fn(), notify: vi.fn() }));
vi.mock("@/lib/kodewavesApi", () => ({ apiFetch: mocks.apiFetch }));
vi.mock("@/context/ClientBrandingContext", () => ({ notifyBrandingChanged: mocks.notify }));

import { ClientBrandingSettingsCard } from "./ClientBrandingSettingsCard";

afterEach(() => { cleanup(); mocks.apiFetch.mockReset(); mocks.notify.mockReset(); });

describe("client branding settings", () => {
  it("shows the normalized brand returned by the server after saving", async () => {
    const initial = { company_name: "Initial", tagline: "Hello", logo_url: "", favicon_url: "", support_email: "", primary_color: "#304c73", font: "geist" };
    mocks.apiFetch.mockResolvedValueOnce(initial).mockResolvedValueOnce({ ...initial, company_name: "Saved Brand" });
    render(<ClientBrandingSettingsCard />);
    const input = await screen.findByLabelText("Display name") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "  Saved Brand  " } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(input.value).toBe("Saved Brand"));
    expect(mocks.notify).toHaveBeenCalledOnce();
  });
});
