"use client";

import {
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Coins,
  CreditCard,
  Flame,
  HelpCircle,
  KeyRound,
  Layers,
  Loader2,
  Lock,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Unlock,
  Zap,
} from "lucide-react";
import React, { useEffect, useState } from "react";

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
import {
  CreditPackage,
  SaaSPlan,
  sovereignBillingApi,
  SovereignWallet,
  WalletLedgerItem,
} from "@/lib/kodewavesApi";

export default function SovereignBillingPage() {
  const [wallet, setWallet] = useState<SovereignWallet | null>(null);
  const [ledger, setLedger] = useState<WalletLedgerItem[]>([]);
  const [plans, setPlans] = useState<SaaSPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [subscribingId, setSubscribingId] = useState<number | null>(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [w, l, p] = await Promise.all([
        sovereignBillingApi.getWallet().catch(() => ({
          balance_minutes: 120.0,
          total_credited_minutes: 200.0,
          total_consumed_minutes: 80.0,
          low_balance_threshold: 15.0,
          plan_name: "Starter",
          plan_minutes: 500,
        })),
        sovereignBillingApi.getLedger().catch(() => []),
        sovereignBillingApi.getPlans().catch(() => []),
      ]);
      setWallet(w);
      setLedger(l);
      setPlans(p);
    } catch (err) {
      console.error("Failed to load billing details:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleSubscribe = async (plan: SaaSPlan) => {
    if (!confirm(`Subscribe to ${plan.name} for ₹${plan.monthly_price_inr.toLocaleString()} / month?`)) return;
    setSubscribingId(plan.id);
    try {
      await sovereignBillingApi.subscribe(plan.id);
      alert(`Successfully subscribed to ${plan.name}! Your minute quota has been updated.`);
      await fetchData();
    } catch (err: any) {
      alert(err.message || "Failed to update subscription");
    } finally {
      setSubscribingId(null);
    }
  };

  return (
    <div className="space-y-8 p-6 md:p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Sovereign Billing & Minute Wallet</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Monitor voice call minutes, review consumption ledgers, and manage your organization subscription.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="outline" className="px-3 py-1 bg-emerald-500/10 text-emerald-600 border-emerald-500/20 text-xs gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5" /> Direct Local Wallet (Zero Dograh Cloud Tolls)
          </Badge>
          <Button variant="outline" size="sm" onClick={fetchData} disabled={loading} className="gap-2">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* WALLET KPI CARDS */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card className="border-border/60 bg-gradient-to-br from-card to-muted/20">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground uppercase">Available Voice Balance</CardTitle>
            <Clock className="h-5 w-5 text-emerald-500" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-extrabold text-emerald-600 dark:text-emerald-400">
              {wallet?.balance_minutes?.toFixed(1) ?? "0.0"} <span className="text-sm font-semibold">mins</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Active voice sessions deduct from this balance per minute
            </p>
          </CardContent>
        </Card>

        <Card className="border-border/60">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground uppercase">Active Subscription Tier</CardTitle>
            <Zap className="h-5 w-5 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-extrabold capitalize">
              {wallet?.plan_name || "Starter"}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Includes {wallet?.plan_minutes ?? 500} minutes / month
            </p>
          </CardContent>
        </Card>

        <Card className="border-border/60">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground uppercase">Total Minutes Delivered</CardTitle>
            <Coins className="h-5 w-5 text-amber-500" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-extrabold text-amber-500">
              {wallet?.total_consumed_minutes?.toFixed(1) ?? "0.0"} <span className="text-sm font-semibold">mins</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Lifetime completed call audio time
            </p>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="plans" className="space-y-6">
        <TabsList className="grid w-full max-w-md grid-cols-2">
          <TabsTrigger value="plans" className="gap-2">
            <CreditCard className="h-4 w-4" />
            Subscription Plans
          </TabsTrigger>
          <TabsTrigger value="ledger" className="gap-2">
            <Layers className="h-4 w-4" />
            Wallet Ledger History
          </TabsTrigger>
        </TabsList>

        {/* PLANS TAB */}
        <TabsContent value="plans" className="space-y-6">
          <div className="grid gap-6 md:grid-cols-3">
            {plans.map((p) => {
              const isCurrent = wallet?.plan_name?.toLowerCase() === p.code.toLowerCase() || wallet?.plan_name?.toLowerCase() === p.name.toLowerCase();
              return (
                <Card
                  key={p.id}
                  className={`border-border/60 flex flex-col justify-between transition-all ${
                    isCurrent ? "border-primary ring-1 ring-primary shadow-md" : "hover:border-primary/40"
                  }`}
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
                    <CardDescription>{p.description || "Production Voice AI agent tier"}</CardDescription>
                    <div className="pt-4">
                      <div className="flex items-baseline gap-1">
                        <span className="text-3xl font-extrabold">₹{p.monthly_price_inr.toLocaleString()}</span>
                        <span className="text-xs text-muted-foreground">/ month</span>
                      </div>
                      <div className="text-xs text-muted-foreground">(${p.monthly_price_usd} USD)</div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="space-y-2 text-xs">
                      <div className="flex items-center justify-between py-1 border-b border-border/40">
                        <span className="text-muted-foreground">Included Monthly Minutes:</span>
                        <span className="font-bold text-foreground font-mono">{p.included_minutes.toLocaleString()} mins</span>
                      </div>
                      <div className="flex items-center justify-between py-1 border-b border-border/40">
                        <span className="text-muted-foreground">Concurrent Calls:</span>
                        <span className="font-bold text-foreground font-mono">{p.max_concurrent_calls} channels</span>
                      </div>
                      <div className="flex items-center justify-between py-1 border-b border-border/40">
                        <span className="text-muted-foreground">Overage Rate:</span>
                        <span className="font-bold text-foreground font-mono">₹{p.overage_rate_per_minute.toFixed(2)}/min</span>
                      </div>
                      <div className="flex items-center justify-between py-1">
                        <span className="text-muted-foreground">BYOK Key Policy:</span>
                        {p.allow_user_byok ? (
                          <Badge variant="outline" className="text-[10px] text-indigo-500 border-indigo-500/30 gap-1">
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
                      disabled={isCurrent || subscribingId === p.id}
                      onClick={() => handleSubscribe(p)}
                    >
                      {subscribingId === p.id && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                      {isCurrent ? "Active Plan" : "Upgrade Plan"}
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </TabsContent>

        {/* LEDGER TAB */}
        <TabsContent value="ledger" className="space-y-6">
          <Card className="border-border/60">
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
                      ledger.map((item) => (
                        <TableRow key={item.id} className="hover:bg-muted/20">
                          <TableCell className="text-xs font-mono text-muted-foreground">
                            {new Date(item.created_at).toLocaleString()}
                          </TableCell>
                          <TableCell className="text-xs font-medium">{item.reason}</TableCell>
                          <TableCell className="text-xs font-mono text-muted-foreground">
                            {item.reference_id || "—"}
                          </TableCell>
                          <TableCell className="text-xs text-right font-mono font-bold">
                            {item.delta_minutes > 0 ? (
                              <span className="text-emerald-500 flex items-center justify-end gap-1">
                                <ArrowUpRight className="h-3.5 w-3.5" /> +{item.delta_minutes.toFixed(1)} m
                              </span>
                            ) : (
                              <span className="text-destructive flex items-center justify-end gap-1">
                                <ArrowDownRight className="h-3.5 w-3.5" /> {item.delta_minutes.toFixed(1)} m
                              </span>
                            )}
                          </TableCell>
                          <TableCell className="text-xs text-right font-mono font-bold text-foreground">
                            {item.balance_after.toFixed(1)} mins
                          </TableCell>
                        </TableRow>
                      ))
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
