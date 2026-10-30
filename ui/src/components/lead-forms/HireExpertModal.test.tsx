import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  user: null as null | { email?: string; primaryEmail?: string },
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: mocks.user }) }));
vi.mock("@/context/AppConfigContext", () => ({
  useAppConfig: () => ({ config: { deploymentMode: "cloud" } }),
}));
vi.mock("@calcom/embed-react", () => ({ default: () => null }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("./CaptchaChallenge", () => ({ CaptchaChallenge: () => null }));
vi.mock("./FormTrustLine", () => ({ FormTrustLine: () => <p>We respect your privacy.</p> }));
vi.mock("./PhoneField", () => ({
  PhoneField: ({ id, value, onChange }: { id: string; value: string; onChange: (value: string) => void }) => (
    <input id={id} aria-label="Phone" value={value} onChange={(event) => onChange(event.target.value)} />
  ),
}));

import { HireExpertModal } from "./HireExpertModal";

describe("HireExpertModal", () => {
  beforeEach(() => {
    mocks.user = null;
  });

  it("leaves the installer placeholder email blank while keeping the form editable and initially disabled", () => {
    mocks.user = { email: " Admin@Admin.com " };
    render(<HireExpertModal open onOpenChange={vi.fn()} source="sidebar" onOpenEnterprise={vi.fn()} />);

    const email = screen.getByLabelText("Email") as HTMLInputElement;
    expect(email.value).toBe("");
    expect((screen.getByRole("button", { name: "Submit" }) as HTMLButtonElement).disabled).toBe(true);

    email.focus();
    expect(document.activeElement).toBe(email);
    fireEvent.change(email, { target: { value: "person@example.com" } });
    expect(email.value).toBe("person@example.com");
    expect((screen.getByRole("button", { name: "Submit" }) as HTMLButtonElement).disabled).toBe(true);

    // The two-column rows collapse naturally below the `sm` breakpoint.
    const nameField = screen.getByLabelText("Name");
    expect(nameField.parentElement?.parentElement?.classList.contains("sm:grid-cols-2")).toBe(true);
  });

  it("prefills an authenticated user's real email, but leaves it editable", () => {
    mocks.user = { primaryEmail: "owner@company.example" };
    render(<HireExpertModal open onOpenChange={vi.fn()} source="sidebar" onOpenEnterprise={vi.fn()} />);

    const email = screen.getByLabelText("Email") as HTMLInputElement;
    expect(email.value).toBe("owner@company.example");
    fireEvent.change(email, { target: { value: "alternate@company.example" } });
    expect(email.value).toBe("alternate@company.example");
  });
});
