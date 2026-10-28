import { describe, expect, it } from "vitest";

import { getPostAuthDestination, getPricingSelection } from "./pricingSelection";

describe("pricing selection redirects", () => {
  it("keeps a valid plan and billing cycle through local authentication", () => {
    expect(getPostAuthDestination("?plan=pro&billing_cycle=annual"))
      .toBe("/billing-sovereign?plan=pro&billing_cycle=annual");
  });

  it("ignores unsupported cycles and rejects unsafe plan codes", () => {
    expect(getPricingSelection("?plan=starter&billing_cycle=quarterly"))
      .toEqual({ plan: "starter" });
    expect(getPostAuthDestination("?plan=..%2Fadmin"))
      .toBe("/after-sign-in");
  });

  it("preserves a valid credit package selection without allowing redirect URLs", () => {
    expect(getPostAuthDestination("?credit_package=starter_bundle-1"))
      .toBe("/billing-sovereign?credit_package=starter_bundle-1");
    expect(getPostAuthDestination("?credit_package=https%3A%2F%2Fevil.example"))
      .toBe("/after-sign-in");
  });
});
