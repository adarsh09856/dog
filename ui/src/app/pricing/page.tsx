"use client";

import { ArrowRight, Check, ChevronDown, Globe2, Server } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { PublicFooter, PublicHeader } from "@/components/PublicSiteChrome";
import { Button } from "@/components/ui/button";
import {
  publicApi,
  type PublicCreditPackage,
  type PublicSaaSPlan,
} from "@/lib/kodewavesApi";

function money(cents: number, currency: string) {
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency,
      maximumFractionDigits: cents % 100 === 0 ? 0 : 2,
    }).format(cents / 100);
  } catch {
    return `${currency} ${(cents / 100).toFixed(2)}`;
  }
}

const faqs = [
  {
    q: "What is included in the displayed price?",
    a: "Each card shows the configured plan amount and enabled features. A monthly selection is a one-time payment for 30 days of plan access; an annual selection is a one-time payment for 365 days. Plans do not renew automatically. A free plan grants its configured trial minutes once when activated; paid plans credit configured minutes once per payment. Minutes do not replenish monthly. Telephony, model providers and infrastructure may add separate costs.",
  },
  {
    q: "Can I use my own model provider keys?",
    a: "Plans that enable bring-your-own-provider keys list this in their features. Your provider bills its usage separately, according to its own rates and terms.",
  },
  {
    q: "How do annual plans work?",
    a: "An annual amount appears only when configured. It is a one-time checkout for 365 days of plan access. It does not renew automatically; included minutes are credited once with that payment, not monthly.",
  },
  {
    q: "Can I deploy the platform on my own server?",
    a: "A client installation requires its own installation license and server capacity. The scope depends on your models, expected simultaneous calls, provider connections and support needs. Hosted subscription prices do not include a private installation.",
  },
  {
    q: "Which languages are available?",
    a: "Available languages and voices come from the STT and TTS models enabled for your agent. Support differs by model and deployment, so confirm that both selected models support each required language and code-switching pattern before launch.",
  },
  {
    q: "Do credits or included minutes expire?",
    a: "Plan access lasts 30 days for a monthly selection or 365 days for an annual selection, then falls back to the configured default plan unless you pay to renew. Renewing the same plan adds time after its current expiry. Switching to a different plan starts a new term immediately; unused time on the previous plan is not carried over. Free-plan trial minutes are granted once at activation; paid-plan minutes are credited once per payment. They do not replenish monthly, and wallet minutes remain available until used.",
  },
];

export default function PricingPage() {
  const [plans, setPlans] = useState<PublicSaaSPlan[]>([]);
  const [packages, setPackages] = useState<PublicCreditPackage[]>([]);
  const [planState, setPlanState] = useState("loading");
  const [packageState, setPackageState] = useState("loading");
  const [reloadKey, setReloadKey] = useState(0);
  const [annual, setAnnual] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  useEffect(() => {
    let active = true;
    setPlanState("loading");
    setPackageState("loading");
    void publicApi.getPublicPlans().then(
      (result) => {
        if (!active) return;
        setPlans(result.filter((plan) => plan.is_active));
        setPlanState("ready");
      },
      () => {
        if (!active) return;
        setPlans([]);
        setPlanState("error");
      },
    );
    void publicApi.getPublicCreditOffers().then(
      (result) => {
        if (!active) return;
        setPackages(result);
        setPackageState("ready");
      },
      () => {
        if (!active) return;
        setPackages([]);
        setPackageState("error");
      },
    );
    return () => {
      active = false;
    };
  }, [reloadKey]);
  const hasCycleChoice = plans.some(
    (plan) => plan.monthly_price_cents > 0 && plan.annual_price_cents > 0,
  );

  return (
    <div className="min-h-screen bg-background text-foreground">
      <PublicHeader />
      <main id="main-content" className="mx-auto max-w-7xl px-5 pb-24 sm:px-8">
        <section className="grid gap-8 border-b border-border py-14 sm:py-20 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
          <div className="max-w-2xl">
            <p className="mb-5 inline-flex items-center gap-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              <span className="h-px w-8 bg-cta" aria-hidden="true" />
              Plans and deployment
            </p>
            <h1 className="text-4xl font-semibold leading-[1.08] tracking-[-0.035em] sm:text-5xl lg:text-6xl">
              Compare plans for your voice operation.
            </h1>
            <p className="mt-6 max-w-xl text-base leading-7 text-muted-foreground sm:text-lg sm:leading-8">
              See the configured price, included usage and enabled features for each workspace plan. Provider and deployment costs are shown separately.
            </p>
          </div>
          {hasCycleChoice && (
            <div
              className="inline-flex h-fit rounded-md border border-border bg-muted/60 p-1 md:mb-1"
              aria-label="Billing period"
            >
              <button
                type="button"
                aria-pressed={!annual}
                onClick={() => setAnnual(false)}
                className={`rounded px-4 py-2 text-sm font-medium transition-colors ${!annual ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
              >
                Monthly
              </button>
              <button
                type="button"
                aria-pressed={annual}
                onClick={() => setAnnual(true)}
                className={`rounded px-4 py-2 text-sm font-medium transition-colors ${annual ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
              >
                Annual
              </button>
            </div>
          )}
        </section>

        <section
          aria-label="Subscription plans"
          className={`grid gap-4 ${planState === "ready" && plans.length === 1
            ? "mx-auto max-w-xl"
            : planState === "ready" && plans.length === 2
              ? "mx-auto max-w-5xl md:grid-cols-2"
              : "md:grid-cols-2 xl:grid-cols-3"}`}
        >
          {planState === "loading" && (
            <p
              role="status"
              className="py-10 text-center text-muted-foreground md:col-span-2 xl:col-span-3"
            >
              Loading current plans…
            </p>
          )}
          {planState === "error" && (
            <div
              role="alert"
              className="rounded-2xl border border-border bg-card p-8 text-center md:col-span-2 xl:col-span-3"
            >
              <p className="mb-4 text-muted-foreground">
                Plans could not be loaded. Prices are hidden until they can be
                verified.
              </p>
              <Button
                variant="outline"
                onClick={() => setReloadKey((key) => key + 1)}
              >
                Retry
              </Button>
            </div>
          )}
          {planState === "ready" && plans.length === 0 && (
            <div className="rounded-2xl border border-border bg-card p-10 text-center md:col-span-2 xl:col-span-3">
              <h2 className="text-xl font-medium">Plans are being prepared.</h2>
              <p className="mt-3 text-sm text-muted-foreground">
                No active subscription plans are published right now. Existing
                customers can sign in to review their account.
              </p>
              <Link
                href="/auth/login"
                className="mt-5 inline-flex text-sm font-semibold text-cta-text"
              >
                Sign in to your account →
              </Link>
            </div>
          )}
          {plans.map((plan) => {
            const hasMonthlyOffer = plan.monthly_price_cents > 0;
            const hasAnnualOffer = plan.annual_price_cents > 0;
            const billingCycle =
              hasMonthlyOffer && hasAnnualOffer
                ? annual
                  ? "annual"
                  : "monthly"
                : hasAnnualOffer
                  ? "annual"
                  : hasMonthlyOffer
                    ? "monthly"
                    : null;
            const price = billingCycle === "annual"
              ? plan.annual_price_cents
              : plan.monthly_price_cents;
            const available = billingCycle !== null && Number.isFinite(price) && Boolean(plan.currency);
            return (
              <article
                key={plan.id}
                className="flex flex-col rounded-lg border border-border bg-card p-6 transition-colors hover:border-foreground/20 sm:p-7"
              >
                <h2 className="text-xl font-semibold tracking-tight">
                  {plan.name}
                </h2>
                <p className="mt-3 min-h-12 text-sm leading-6 text-muted-foreground">
                  {plan.description ||
                    "A configured workspace plan for your voice agents."}
                </p>
                <div className="my-7 border-y border-border py-5">
                  <p className="text-4xl font-semibold tracking-tight tabular-nums">
                    {available ? money(price, plan.currency) : billingCycle ? "Price unavailable" : "Free"}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {billingCycle
                      ? `${plan.currency} · one-time payment for ${billingCycle === "annual" ? "365 days" : "30 days"} of access`
                      : "No payment required for this plan"}
                  </p>
                </div>
                <ul className="mb-8 space-y-3 text-sm">
                  <li className="flex gap-3">
                    <Check className="size-4 shrink-0 text-cta-text" />
                    {plan.included_minutes.toLocaleString()} {billingCycle
                      ? "minutes credited per payment"
                      : "one-time trial minutes on activation"}
                  </li>
                  <li className="flex gap-3">
                    <Check className="size-4 shrink-0 text-cta-text" />
                    {plan.max_agents.toLocaleString()} agents
                  </li>
                  <li className="flex gap-3">
                    <Check className="size-4 shrink-0 text-cta-text" />
                    {plan.max_concurrent_calls.toLocaleString()} concurrent
                    calls
                  </li>
                  {plan.features?.map((feature) => (
                    <li key={feature} className="flex gap-3">
                      <Check className="size-4 shrink-0 text-cta-text" />
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>
                <Link
                  href={`/auth/login?plan=${encodeURIComponent(plan.code)}${billingCycle ? `&billing_cycle=${billingCycle}` : ""}`}
                  className="mt-auto inline-flex items-center justify-between gap-3 rounded-md border border-border px-4 py-3 text-sm font-semibold transition-colors hover:border-cta/50 hover:bg-muted"
                >
                  Review in your account
                  <ArrowRight className="size-4" />
                </Link>
              </article>
            );
          })}
        </section>
        <p className="mx-auto mt-7 max-w-3xl text-center text-xs leading-6 text-muted-foreground">
          Prices are shown in each offer’s configured currency. No currency
          conversion or annual discount is estimated here. Taxes and final
          payment terms are confirmed during purchase.
        </p>

        <section className="mt-24">
          <div className="mb-8">
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-cta-text">
              Additional usage
            </p>
            <h2 className="text-3xl font-medium tracking-tight">
              Credit bundles
            </h2>
            <p className="mt-3 text-sm leading-7 text-muted-foreground">
              Review the available top-ups for your account. Provider and
              carrier charges may apply separately.
            </p>
          </div>
          <div className="grid gap-5 md:grid-cols-3">
            {packageState === "loading" && (
              <p role="status" className="text-sm text-muted-foreground">
                Loading credit bundles…
              </p>
            )}
            {packageState === "error" && (
              <div
                role="alert"
                className="rounded-xl border border-border p-6 md:col-span-3"
              >
                <p className="mb-3 text-sm text-muted-foreground">
                  Credit bundles could not be loaded.
                </p>
                <Button
                  variant="outline"
                  onClick={() => setReloadKey((key) => key + 1)}
                >
                  Retry
                </Button>
              </div>
            )}
            {packageState === "ready" && packages.length === 0 && (
              <p className="text-sm text-muted-foreground md:col-span-3">
                No credit bundles are published right now.
              </p>
            )}
            {packages.map((pkg) => (
              <article
                key={pkg.id}
                className="rounded-2xl border border-border bg-card p-7"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-semibold">{pkg.name}</h3>
                  {pkg.is_popular && <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">Popular</span>}
                </div>
                <p className="mt-5 text-3xl font-medium tracking-tight">
                  {money(pkg.price_cents, pkg.currency)}
                </p>
                <p className="mt-3 text-sm text-muted-foreground">
                  {pkg.minutes.toLocaleString()} minutes
                  {pkg.bonus_minutes > 0
                    ? ` + ${pkg.bonus_minutes.toLocaleString()} bonus minutes`
                    : ""}
                </p>
                <Link
                  href={`/auth/login?credit_package=${encodeURIComponent(String(pkg.id))}`}
                  className="mt-6 inline-flex items-center gap-2 text-sm font-semibold text-cta-text"
                >
                  Continue to wallet
                  <ArrowRight className="size-4" />
                </Link>
              </article>
            ))}
          </div>
        </section>

        <section className="my-24 grid gap-8 rounded-2xl border border-border bg-muted/40 p-7 sm:p-10 md:grid-cols-2">
          <div>
            <Server className="mb-5 size-6 text-cta-text" />
            <h2 className="text-3xl font-medium tracking-tight">
              Planning a client installation?
            </h2>
            <p className="mt-4 text-sm leading-7 text-muted-foreground">
              A client-installed edition requires its own installation license
              and server capacity. Discuss the scope with your platform
              administrator before choosing infrastructure.
            </p>
          </div>
          <div>
            <Globe2 className="mb-5 size-6 text-cta-text" />
            <h3 className="text-lg font-semibold">
              Budget for the complete deployment.
            </h3>
            <ul className="mt-4 space-y-3 text-sm leading-6 text-muted-foreground">
              {[
                "Subscription or installation license",
                "Telephony numbers and carrier usage",
                "Connected speech and language providers",
                "Hosting, storage, support and maintenance",
              ].map((item) => (
                <li key={item} className="flex gap-3">
                  <Check className="mt-1 size-4 shrink-0 text-cta-text" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="mx-auto max-w-3xl">
          <h2 className="mb-8 text-3xl font-medium tracking-tight">
            Questions before you start.
          </h2>
          <div className="divide-y divide-border border-y border-border">
            {faqs.map((faq, index) => (
              <div key={faq.q}>
                <button
                  type="button"
                  aria-expanded={openFaq === index}
                  aria-controls={`pricing-faq-${index}`}
                  onClick={() => setOpenFaq(openFaq === index ? null : index)}
                  className="flex w-full items-center justify-between gap-5 py-6 text-left text-sm font-semibold"
                >
                  {faq.q}
                  <ChevronDown
                    className={`size-4 shrink-0 text-muted-foreground transition-transform ${openFaq === index ? "rotate-180" : ""}`}
                  />
                </button>
                {openFaq === index && (
                  <p
                    id={`pricing-faq-${index}`}
                    className="pb-6 text-sm leading-7 text-muted-foreground"
                  >
                    {faq.a}
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
