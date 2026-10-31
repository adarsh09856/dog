import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("./EnterpriseModal", () => ({
  EnterpriseModal: ({ open, source }: { open: boolean; source: string }) =>
    open ? <div role="dialog" data-source={source}>Enterprise intake</div> : null,
}));

import { PublicEnterpriseLeadCTA } from "./PublicEnterpriseLeadCTA";

describe("PublicEnterpriseLeadCTA", () => {
  it("opens the persisted enterprise intake with the public landing source", () => {
    render(<PublicEnterpriseLeadCTA label="Discuss a client installation" className="cta" />);

    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Discuss a client installation/ }));

    expect(screen.getByRole("dialog").getAttribute("data-source")).toBe("landing_contact");
  });
});
