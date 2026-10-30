"use client";
import {
  ArrowDownRight,
  ArrowUpRight,
  Clock,
  Coins,
  CreditCard,
  Layers,
  Loader2,
  Lock,
  RefreshCw,
  ShieldCheck,
  Unlock,
  Zap,
} from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";

import panel from "@/components/layout/PanelWorkspace.module.css";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useClientBranding } from "@/context/ClientBrandingContext";
import { useAuth } from "@/lib/auth";
import {
  paymentsApi,
  publicApi,
  PublicCreditPackage,
  SaaSPlan,
  sovereignBillingApi,
  SovereignWallet,
  WalletLedgerItem,
} from "@/lib/kodewavesApi";

import styles from "./BillingWorkspace.module.css";

function loadRazorpayCheckout() {
  if (window.Razorpay) return Promise.resolve(true);
  return new Promise<boolean>((resolve) => {
    const existing = document.querySelector<HTMLScriptElement>('script[src="https://checkout.razorpay.com/v1/checkout.js"]');
    const script = existing ?? document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve(Boolean(window.Razorpay));
    script.onerror = () => resolve(false);
    if (!existing) document.body.appendChild(script);
  });
}

function formatMoney(amount: number, currency: string) {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}

function formatMinorUnits(amount: number, currency: string) {
  return formatMoney(amount / 100, currency);
}

export default function SovereignBillingPage() {
  const { user, loading: authLoading } = useAuth();
  const branding = useClientBranding();
  const [wallet, setWallet] = useState<SovereignWallet | null>(null);
  const [ledger, setLedger] = useState<WalletLedgerItem[]>([]);
  const [plans, setPlans] = useState<SaaSPlan[]>([]);
  const [creditPackages, setCreditPackages] = useState<PublicCreditPackage[]>([]);
  const [creditPackagesLoading, setCreditPackagesLoading] = useState(true);
  const [creditPackagesError, setCreditPackagesError] = useState<string | null>(null);
  const [selectedCreditPackage, setSelectedCreditPackage] = useState<string | null>(null);
  const [purchasingPackageId, setPurchasingPackageId] = useState<string | null>(null);
  const [billingCycles, setBillingCycles] = useState<Record<string, "monthly" | "annual">>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [subscribingId, setSubscribingId] = useState<number | string | null>(null);
  const handledStripeSession = useRef<string | null>(null);
  const appliedPricingSelection = useRef(false);
  const appliedCreditSelection = useRef(false);

  const fetchData = useCallback(async () => {
    if (authLoading || !user) return;
    setLoadError(null);
    setLoading(true);
    try {
      const [w, l, p] = await Promise.all([
        sovereignBillingApi.getWallet(),
        sovereignBillingApi.getLedger(),
        sovereignBillingApi.getPlans(),
      ]);
      setWallet(w);
      setLedger(l);
      setPlans(p);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Unable to load this page. Please retry.");
      console.error("Failed to load billing details:", err);
    } finally {
      setLoading(false);
    }
  }, [authLoading, user]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (authLoading || !user) return;
    let active = true;
    setCreditPackagesLoading(true);
    setCreditPackagesError(null);
    void publicApi.getPublicCreditOffers().then(
      (offers) => {
        if (!active) return;
        setCreditPackages(offers);
      },
      () => {
        if (!active) return;
        setCreditPackages([]);
        setCreditPackagesError("Credit bundles could not be loaded. Refresh the page to try again.");
      },
    ).finally(() => {
      if (active) setCreditPackagesLoading(false);
    });
    return () => { active = false; };
  }, [authLoading, user]);

  useEffect(() => {
    if (appliedCreditSelection.current || typeof window === "undefined") return;
    const requestedPackage = new URLSearchParams(window.location.search).get("credit_package");
    if (!requestedPackage || !/^[a-zA-Z0-9_-]{1,80}$/.test(requestedPackage)) return;
    appliedCreditSelection.current = true;
    setSelectedCreditPackage(requestedPackage);
  }, []);

  useEffect(() => {
    if (loading || appliedPricingSelection.current || typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const requestedCode = params.get("plan");
    if (!requestedCode) return;
    appliedPricingSelection.current = true;
    const plan = plans.find((item) => item.code === requestedCode);
    const requestedCycle = params.get("billing_cycle");
    if (!plan || (requestedCycle !== "monthly" && requestedCycle !== "annual")) return;
    const cycleIsAvailable = requestedCycle === "monthly"
      ? plan.monthly_price_cents > 0
      : plan.annual_price_cents > 0;
    const fallbackCycle = plan.monthly_price_cents > 0 ? "monthly" : "annual";
    setBillingCycles((current) => ({
      ...current,
      [String(plan.id)]: cycleIsAvailable ? requestedCycle : fallbackCycle,
    }));
  }, [loading, plans]);

  useEffect(() => {
    if (authLoading || !user || typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("session_id");
    if (params.get("payment") !== "success" || !sessionId || handledStripeSession.current === sessionId) return;
    handledStripeSession.current = sessionId;
    let cancelled = false;
    // A return URL is not payment proof: verify the provider receipt before
    // showing success or refreshing the wallet. Keep the URL on failure so it
    // can be retried after a temporary verification outage.
    void paymentsApi.verifyPayment({ gateway: "stripe", order_id: sessionId, payment_id: sessionId })
      .then(async (receipt) => {
        if (cancelled) return;
        if (!receipt.success) throw new Error("Payment has not been verified. Refresh before retrying payment.");
        window.history.replaceState({}, "", window.location.pathname);
        await fetchData();
        alert(receipt.message);
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "Payment verification failed. Refresh before retrying payment.");
      });
    return () => { cancelled = true; };
  }, [authLoading, fetchData, user]);

  const handleSubscribe = async (plan: SaaSPlan) => {
    const selectedCycle = billingCycles[String(plan.id)] ?? (plan.monthly_price_cents > 0 ? "monthly" : "annual");
    const billingCycle = selectedCycle === "monthly" && plan.monthly_price_cents > 0
      ? "monthly"
      : plan.annual_price_cents > 0 ? "annual" : plan.monthly_price_cents > 0 ? "monthly" : null;
    if (!billingCycle) {
      setSubscribingId(plan.id);
      try {
        await sovereignBillingApi.subscribe(plan.id);
        alert(`Successfully activated ${plan.name}.`);
        await fetchData();
      } catch (err: unknown) {
        alert(err instanceof Error ? err.message : "Failed to activate plan");
      } finally {
        setSubscribingId(null);
      }
      return;
    }
    const price = billingCycle === "annual" ? plan.annual_price_cents : plan.monthly_price_cents;
    const accessDays = billingCycle === "annual" ? 365 : 30;
    const renewal = wallet?.plan_code === plan.code;
    const termNotice = renewal
      ? "Renewing adds this term after your current expiry."
      : "This plan starts immediately and replaces your current plan. Unused time on a different plan is not carried over.";
    if (!confirm(`Pay ${formatMinorUnits(price, plan.currency)} once for ${accessDays} days of ${plan.name} access? ${termNotice} It will not renew automatically. Included minutes are credited once and do not replenish monthly.`)) return;
    setSubscribingId(plan.id);
    try {
      const config = await paymentsApi.getConfig();
      if (config.razorpay_enabled && config.razorpay_key_id) {
        const checkoutReady = await loadRazorpayCheckout();
        if (!checkoutReady || !window.Razorpay) throw new Error("Razorpay checkout could not be loaded. Please retry.");
        const order = await paymentsApi.createOrder({ plan_code: plan.code, gateway: "razorpay", billing_cycle: billingCycle });
        new window.Razorpay({
          key: order.key_id || config.razorpay_key_id,
          amount: order.amount,
          currency: order.currency,
          name: branding.company_name,
          description: `${plan.name} ${billingCycle} plan`,
          order_id: order.order_id,
          handler: async (result) => {
            try {
              const verified = await paymentsApi.verifyPayment({
                gateway: "razorpay",
                order_id: result.razorpay_order_id,
                payment_id: result.razorpay_payment_id,
                signature: result.razorpay_signature,
                plan_code: plan.code,
              });
              alert(verified.message);
              await fetchData();
            } catch (err: unknown) {
              alert(err instanceof Error ? err.message : "Payment verification failed");
            } finally {
              setSubscribingId(null);
            }
          },
          modal: { ondismiss: () => setSubscribingId(null) },
        }).open();
        return;
      }
      if (config.stripe_enabled) {
        const order = await paymentsApi.createOrder({ plan_code: plan.code, gateway: "stripe", billing_cycle: billingCycle });
        if (!order.checkout_url) throw new Error("Stripe did not return a checkout URL");
        window.location.assign(order.checkout_url);
        return;
      }
      throw new Error("Payments are not configured for this platform. Contact the administrator.");
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to update subscription");
      setSubscribingId(null);
    }
  };

  const handleCreditPackagePurchase = async (pkg: PublicCreditPackage) => {
    const packageId = String(pkg.id);
    if (wallet?.is_frozen) return;
    const totalMinutes = pkg.minutes + pkg.bonus_minutes;
    if (!confirm(`Buy ${pkg.name} for ${formatMinorUnits(pkg.price_cents, pkg.currency)}? This is a one-time payment for ${totalMinutes.toLocaleString()} wallet minutes. Provider and carrier charges may apply separately.`)) return;
    setPurchasingPackageId(packageId);
    try {
      const config = await paymentsApi.getConfig();
      if (config.razorpay_enabled && config.razorpay_key_id) {
        const checkoutReady = await loadRazorpayCheckout();
        if (!checkoutReady || !window.Razorpay) throw new Error("Razorpay checkout could not be loaded. Please retry.");
        const order = await paymentsApi.createOrder({ package_id: packageId, gateway: "razorpay" });
        new window.Razorpay({
          key: order.key_id || config.razorpay_key_id,
          amount: order.amount,
          currency: order.currency,
          name: branding.company_name,
          description: `${pkg.name} credit bundle`,
          order_id: order.order_id,
          handler: async (result) => {
            try {
              const verified = await paymentsApi.verifyPayment({
                gateway: "razorpay",
                order_id: result.razorpay_order_id,
                payment_id: result.razorpay_payment_id,
                signature: result.razorpay_signature,
                package_id: packageId,
              });
              alert(verified.message);
              setSelectedCreditPackage(null);
              await fetchData();
            } catch (err: unknown) {
              alert(err instanceof Error ? err.message : "Payment verification failed");
            } finally {
              setPurchasingPackageId(null);
            }
          },
          modal: { ondismiss: () => setPurchasingPackageId(null) },
        }).open();
        return;
      }
      if (config.stripe_enabled) {
        const order = await paymentsApi.createOrder({ package_id: packageId, gateway: "stripe" });
        if (!order.checkout_url) throw new Error("Stripe did not return a checkout URL");
        window.location.assign(order.checkout_url);
        return;
      }
      throw new Error("Payments are not configured for this platform. Contact the administrator.");
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Credit bundle checkout failed");
      setPurchasingPackageId(null);
    }
  };

  return (
    <div className={styles.page}>
      {loadError && <div role="alert" className="rounded-md border border-destructive p-3 text-sm text-destructive">{loadError}</div>}
      {/* Header */}
      <header className={styles.hero}>
        <div className={styles.heroCopy}>
          <span className={styles.eyebrow}>WORKSPACE / BILLING</span><h1>Billing &amp; Minute Wallet</h1>
          <p>
            Monitor voice minutes, review transactions, and manage your organization’s plan access.
          </p>
        </div>
        <div className={styles.heroActions}>
          <Badge variant="outline" className="px-3 py-1 bg-emerald-500/10 text-emerald-600 border-emerald-500/20 text-xs gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5" /> Organization Wallet
          </Badge>
          <Button variant="outline" size="sm" onClick={fetchData} disabled={loading} className="gap-2">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </header>

      {/* WALLET KPI CARDS */}
      <div className={`${panel.billingMetrics} ${styles.metrics}`} aria-label="Wallet summary">
        <Card className="border-border/60 bg-gradient-to-br from-card to-muted/20">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground uppercase">Available Voice Balance</CardTitle>
            <Clock className="h-5 w-5 text-emerald-500" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-extrabold text-emerald-600 dark:text-emerald-400">
              {(wallet?.total_available_minutes ?? ((wallet?.credit_balance_minutes ?? 0) + (wallet?.bonus_minutes ?? 0))).toFixed(1)} <span className="text-sm font-semibold">mins</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Platform-managed voice usage uses these minutes. Calls using only local models or your own provider keys do not use platform minutes.
            </p>
          </CardContent>
        </Card>

        <Card className="border-border/60">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground uppercase">Current Plan Assignment</CardTitle>
            <Zap className="h-5 w-5 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-extrabold capitalize">
              {wallet?.plan_name || "No plan selected"}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {wallet?.included_minutes != null ? `${wallet.included_minutes.toLocaleString()} minutes per payment${wallet.plan_expires_at ? ` · access through ${new Date(wallet.plan_expires_at).toLocaleDateString()}` : " · no expiry recorded"}` : "No active plan assignment"}
            </p>
          </CardContent>
        </Card>

        <Card className="border-border/60">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground uppercase">Wallet Status</CardTitle>
            <Coins className="h-5 w-5 text-amber-500" />
          </CardHeader>
          <CardContent>
            <div className={`text-3xl font-extrabold ${wallet?.is_frozen ? "text-destructive" : "text-emerald-600 dark:text-emerald-400"}`}>
              {!wallet ? "Loading" : wallet.is_frozen ? "Frozen" : "Active"}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {!wallet ? "Checking organization wallet…" : wallet.is_frozen ? "Wallet transactions are currently paused" : "Organization wallet can receive and use credits"}
            </p>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="plans" className={styles.planArea}>
        <TabsList className={`${styles.tabList} grid grid-cols-2`}>
          <TabsTrigger value="plans" className="gap-2">
            <CreditCard className="h-4 w-4" />
            Plan Options
          </TabsTrigger>
          <TabsTrigger value="ledger" className="gap-2">
            <Layers className="h-4 w-4" />
            Wallet Ledger History
          </TabsTrigger>
        </TabsList>

        {/* PLANS TAB */}
        <TabsContent value="plans" className="space-y-6">
          <div className={styles.sectionIntro}><div><h2>Choose a plan</h2><p>Compare included voice minutes, concurrency, and key policies. Plans are paid once for a fixed access term.</p></div></div>
          <div className={styles.planGrid}>
            {plans.map((p) => {
              const isCurrent = wallet?.plan_code === p.code;
              const selectedCycle = billingCycles[String(p.id)] ?? (p.monthly_price_cents > 0 ? "monthly" : "annual");
              const selectedPrice = selectedCycle === "annual" && p.annual_price_cents > 0
                ? p.annual_price_cents
                : p.monthly_price_cents;
              const selectedAccessDays = selectedCycle === "annual" && p.annual_price_cents > 0 ? 365 : 30;
              const isPaidPlan = p.monthly_price_cents > 0 || p.annual_price_cents > 0;
              return (
                <Card
                  key={p.id}
                  className={`${styles.planCard} flex flex-col justify-between transition-all ${
                    isCurrent ? "border-primary ring-1 ring-primary shadow-md" : "hover:border-primary/40"
                  } ${isCurrent ? styles.planCardCurrent : ""}`}
                >
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg">{p.name}</CardTitle>
                      {isCurrent && (
                        <Badge className="bg-primary text-primary-foreground text-[10px]">
                          Current Plan
                        </Badge>
                      )}
                    </div>
                    <CardDescription>{p.description || "Voice AI agent plan"}</CardDescription>
                    <div className={`${styles.planPrice} pt-4`}>
                      <div className="flex items-baseline gap-1">
                        <span className="text-3xl font-extrabold">{isPaidPlan ? formatMinorUnits(selectedPrice, p.currency) : "Free"}</span>
                        {isPaidPlan ? <span className="text-xs text-muted-foreground">· one-time payment for {selectedAccessDays} days</span> : null}
                      </div>
                      {p.monthly_price_cents > 0 && p.annual_price_cents > 0 ? (
                        <div className="mt-3 inline-flex rounded-lg border border-border p-1" role="group" aria-label={`${p.name} billing cycle`}>
                          <button
                            type="button"
                            aria-pressed={selectedCycle === "monthly"}
                            className={`rounded-md px-3 py-1.5 text-xs ${selectedCycle === "monthly" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}
                            onClick={() => setBillingCycles((current) => ({ ...current, [String(p.id)]: "monthly" }))}
                          >
                            Monthly
                          </button>
                          <button
                            type="button"
                            aria-pressed={selectedCycle === "annual"}
                            className={`rounded-md px-3 py-1.5 text-xs ${selectedCycle === "annual" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}
                            onClick={() => setBillingCycles((current) => ({ ...current, [String(p.id)]: "annual" }))}
                          >
                            Annual
                          </button>
                        </div>
                      ) : null}
                      <p className="mt-2 text-xs text-muted-foreground">{isPaidPlan ? `No automatic renewal. Access lasts ${selectedAccessDays} days. Included minutes are credited once per payment.` : "No automatic renewal. Included minutes are credited once on activation."}</p>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="space-y-2 text-xs">
                      <div className="flex items-center justify-between py-1 border-b border-border/40">
                        <span className="text-muted-foreground">{isPaidPlan ? "Minutes per payment:" : "One-time trial minutes:"}</span>
                        <span className="font-bold text-foreground font-mono">{p.included_minutes.toLocaleString()} mins</span>
                      </div>
                      <div className="flex items-center justify-between py-1 border-b border-border/40">
                        <span className="text-muted-foreground">Concurrent Calls:</span>
                        <span className="font-bold text-foreground font-mono">{p.max_concurrent_calls} channels</span>
                      </div>
                      <div className="flex items-center justify-between py-1">
                        <span className="text-muted-foreground">BYOK Key Policy:</span>
                        {p.allow_user_byok ? (
                          <Badge variant="outline" className="text-[10px] text-primary border-primary/30 gap-1">
                            <Unlock className="h-3 w-3" /> BYOK Allowed
                          </Badge>
                        ) : (
                          <Badge className="bg-amber-500/10 text-amber-600 border-amber-500/20 text-[10px] gap-1 hover:bg-amber-500/20">
                            <Lock className="h-3 w-3" /> Platform Managed
                          </Badge>
                        )}
                      </div>
                    </div>

                    <Button
                      className="w-full mt-4"
                      variant={isCurrent ? "outline" : "default"}
                      disabled={(isCurrent && !isPaidPlan) || subscribingId !== null}
                      onClick={() => handleSubscribe(p)}
                    >
                      {subscribingId === p.id && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                      {isCurrent ? (isPaidPlan ? "Renew Plan" : "Active Plan") : "Choose Plan"}
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          <section aria-labelledby="credit-bundles-heading" className={styles.creditSection}>
            <div className={styles.sectionIntro}>
              <div>
              <h2 id="credit-bundles-heading" className="text-xl font-semibold">Credit bundles</h2>
              <p className="mt-1 text-sm text-muted-foreground">One-time wallet top-ups. Provider and carrier costs may be billed separately.</p>
              </div>
            </div>
            {selectedCreditPackage && (
              <p role="status" className="rounded-md border border-primary/40 bg-primary/5 p-3 text-sm">
                You selected a bundle from public pricing. Review it below and confirm before checkout.
              </p>
            )}
            {creditPackagesError && <p role="alert" className="text-sm text-destructive">{creditPackagesError}</p>}
            {creditPackagesLoading ? (
              <p role="status" className="text-sm text-muted-foreground">Loading credit bundles…</p>
            ) : creditPackages.length === 0 ? (
              <p className="text-sm text-muted-foreground">No credit bundles are currently published.</p>
            ) : (
              <div className={styles.creditGrid}>
                {creditPackages.map((pkg) => {
                  const packageId = String(pkg.id);
                  const selected = selectedCreditPackage === packageId;
                  const totalMinutes = pkg.minutes + pkg.bonus_minutes;
                  return (
                    <Card key={packageId} id={`credit-package-${packageId}`} className={`${styles.creditCard} flex flex-col ${selected ? styles.creditCardSelected : ""}`}>
                      <CardHeader>
                        <div className="flex flex-wrap items-center gap-2">
                          <CardTitle className="text-base">{pkg.name}</CardTitle>
                          {pkg.is_popular && <Badge variant="secondary">Popular</Badge>}
                        </div>
                        <CardDescription>{pkg.minutes.toLocaleString()} minutes{pkg.bonus_minutes > 0 ? ` + ${pkg.bonus_minutes.toLocaleString()} bonus` : ""} · one-time</CardDescription>
                        <p className="pt-2 text-2xl font-bold">{formatMinorUnits(pkg.price_cents, pkg.currency)}</p>
                      </CardHeader>
                      <CardContent className="mt-auto space-y-3">
                        <p className="text-xs text-muted-foreground">Adds {totalMinutes.toLocaleString()} wallet minutes. No expiry is applied to the wallet credit.</p>
                        <Button className="w-full" variant={selected ? "default" : "outline"} disabled={Boolean(wallet?.is_frozen) || purchasingPackageId !== null} onClick={() => handleCreditPackagePurchase(pkg)}>
                          {purchasingPackageId === packageId && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                          {purchasingPackageId === packageId ? "Opening checkout…" : selected ? "Continue to payment" : "Buy bundle"}
                        </Button>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </section>
        </TabsContent>

        {/* LEDGER TAB */}
        <TabsContent value="ledger" className={styles.ledgerArea}>
          <Card className={styles.ledgerCard}>
            <CardHeader>
              <CardTitle className="text-base">Wallet Minute Ledger</CardTitle>
              <CardDescription>
                Detailed audit statement of voice minute debits and credit top-ups for your organization.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <div className="rounded-lg overflow-hidden">
                <Table>
                  <TableHeader className="bg-muted/40">
                    <TableRow>
                      <TableHead className="text-xs">Date & Time</TableHead>
                      <TableHead className="text-xs">Transaction Reason</TableHead>
                      <TableHead className="text-xs">Reference ID</TableHead>
                      <TableHead className="text-xs text-right">Delta Minutes</TableHead>
                      <TableHead className="text-xs text-right font-bold">Balance After</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {ledger.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="text-center py-12 text-sm text-muted-foreground">
                          No ledger transactions recorded yet. Minutes will deduct as voice calls complete.
                        </TableCell>
                      </TableRow>
                    ) : (
                      ledger.map((item) => {
                        const delta = item.amount_minutes ?? item.delta_minutes ?? 0;
                        const bal = item.balance_after;
                        return (
                          <TableRow key={item.id} className="hover:bg-muted/20">
                            <TableCell className="text-xs font-mono text-muted-foreground">
                              {new Date(item.created_at).toLocaleString()}
                            </TableCell>
                            <TableCell className="text-xs font-medium">{item.reason}</TableCell>
                            <TableCell className="text-xs font-mono text-muted-foreground">
                              {item.reference_id || "—"}
                            </TableCell>
                            <TableCell className="text-xs text-right font-mono font-bold">
                              {delta >= 0 ? (
                                <span className="text-emerald-500 flex items-center justify-end gap-1">
                                  <ArrowUpRight className="h-3.5 w-3.5" /> +{delta.toFixed(1)} m
                                </span>
                              ) : (
                                <span className="text-destructive flex items-center justify-end gap-1">
                                  <ArrowDownRight className="h-3.5 w-3.5" /> {delta.toFixed(1)} m
                                </span>
                              )}
                            </TableCell>
                            <TableCell className="text-xs text-right font-mono font-bold text-foreground">
                              {bal.toFixed(1)} mins
                            </TableCell>
                          </TableRow>
                        );
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
