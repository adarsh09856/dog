export type BillingCycle = "monthly" | "annual";

/** Keep only catalog-style plan identifiers and supported billing periods. */
export function getPricingSelection(search: string): { plan: string; billingCycle?: BillingCycle } | null {
  const params = new URLSearchParams(search);
  const plan = params.get("plan");
  if (!plan || !/^[a-zA-Z0-9_-]{1,80}$/.test(plan)) return null;

  const cycle = params.get("billing_cycle");
  return {
    plan,
    ...(cycle === "monthly" || cycle === "annual" ? { billingCycle: cycle } : {}),
  };
}

export function getPostAuthDestination(search: string): string {
  const params = new URLSearchParams(search);
  const creditPackage = params.get("credit_package");
  if (creditPackage && /^[a-zA-Z0-9_-]{1,80}$/.test(creditPackage)) {
    return `/billing-sovereign?credit_package=${encodeURIComponent(creditPackage)}`;
  }
  const selection = getPricingSelection(search);
  if (!selection) return "/after-sign-in";
  const destinationParams = new URLSearchParams({ plan: selection.plan });
  if (selection.billingCycle) destinationParams.set("billing_cycle", selection.billingCycle);
  return `/billing-sovereign?${destinationParams.toString()}`;
}
