"use client";

import admin from "../AdminWorkspace.module.css";

import {
  Edit,
  KeyRound,
  Loader2,
  Lock,
  Plus,
  RefreshCw,
  Trash2,
  Unlock,
} from "lucide-react";
import React, { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { adminApi, SaaSPlan } from "@/lib/kodewavesApi";

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

export default function AdminPlansPage() {
  const [plans, setPlans] = useState<SaaSPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal
  const [modalOpen, setModalOpen] = useState(false);
  const [editingPlan, setEditingPlan] = useState<Partial<SaaSPlan> | null>(null);
  const [saving, setSaving] = useState(false);

  const fetchPlans = useCallback(async () => {
    setLoading(true);
    try {
      const data = await adminApi.getPlans();
      setPlans(data);
      setError(null);
    } catch (err) {
      console.error("Failed to load plans:", err);
      setError(err instanceof Error ? err.message : "Failed to load plans");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPlans();
  }, [fetchPlans]);

  const handleSave = async () => {
    if (!editingPlan || !editingPlan.name || !editingPlan.code) return;
    setSaving(true);
    try {
      if (editingPlan.id) {
        await adminApi.updatePlan(editingPlan.id, editingPlan);
      } else {
        await adminApi.createPlan(editingPlan);
      }
      setModalOpen(false);
      setEditingPlan(null);
      await fetchPlans();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to save SaaS plan");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number | string) => {
    if (!confirm("Are you sure you want to delete this plan?")) return;
    try {
      await adminApi.deletePlan(id);
      await fetchPlans();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete plan");
    }
  };

  return (
    <div className={admin.surface} data-area="COMMERCE / PLANS">
      {/* Header */}
      <div className={admin.hero}>
        <div>
          <span className={admin.kicker}>COMMERCE / PLANS</span>
          <h1 className={admin.title}>SaaS Plans</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure 30-day and 365-day access with manual renewal. Included minutes are credited once per purchase.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            className="gap-2"
            onClick={() => {
              setEditingPlan({
                name: "New Tier",
                code: "new-tier",
                monthly_price_cents: 499900,
                annual_price_cents: 0,
                currency: "INR",
                included_minutes: 1000,
                max_concurrent_calls: 5,
                max_agents: 3,
                has_crm_access: true,
                has_appointments_access: true,
                has_forms_access: true,
                has_widget_access: true,
                has_campaigns_access: true,
                allow_user_byok: false,
                is_active: true,
                is_public: true,
              });
              setModalOpen(true);
            }}
          >
            <Plus className="h-4 w-4" /> Create Plan
          </Button>
          <Button variant="outline" size="sm" onClick={fetchPlans} disabled={loading} className="gap-2">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {error && <p role="alert" className="text-sm text-destructive">{error} Use Refresh to retry.</p>}

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            <span>Available Tiers ({plans.length})</span>
            <Badge variant="outline" className="text-xs">
              Direct Local Wallet Billing
            </Badge>
          </CardTitle>
          <CardDescription>
            When &quot;Allow BYOK&quot; is disabled on a plan, subscribers cannot use their own API keys and must consume platform-managed credits.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-border/60 overflow-hidden">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow>
                  <TableHead className="text-xs">Plan Name</TableHead>
                  <TableHead className="text-xs">Code</TableHead>
                  <TableHead className="text-xs text-right">Configured monthly price</TableHead>
                  <TableHead className="text-xs text-right">Included Mins</TableHead>
                  <TableHead className="text-xs text-center">Concurrency</TableHead>
                  <TableHead className="text-xs text-center">BYOK Policy</TableHead>
                  <TableHead className="text-xs text-center">Status</TableHead>
                  <TableHead className="text-xs text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading || error ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center py-8 text-sm text-muted-foreground">
                      {loading ? "Loading plans…" : "Plans could not be loaded. Refresh to retry."}
                    </TableCell>
                  </TableRow>
                ) : plans.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center py-8 text-sm text-muted-foreground">
                      No plans created yet. Click &quot;Create Plan&quot; to build your first tier.
                    </TableCell>
                  </TableRow>
                ) : (
                  plans.map((p) => (
                    <TableRow key={p.id} className="hover:bg-muted/20">
                      <TableCell className="font-semibold text-xs">{p.name}</TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">{p.code}</TableCell>
                      <TableCell className="text-xs text-right font-mono font-medium">
                        {formatMoney(p.monthly_price_cents / 100, p.currency)} / month
                        {p.annual_price_cents > 0 ? (
                          <span className="block text-muted-foreground">
                            {formatMoney(p.annual_price_cents / 100, p.currency)} / year
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-xs text-right font-mono font-bold text-emerald-600 dark:text-emerald-400">
                        {p.included_minutes.toLocaleString()} mins
                      </TableCell>
                      <TableCell className="text-center font-mono text-xs">{p.max_concurrent_calls} calls</TableCell>
                      <TableCell className="text-center">
                        {p.allow_user_byok ? (
                          <Badge variant="outline" className="text-[10px] text-primary border-primary/30 gap-1">
                            <Unlock className="h-3 w-3" /> BYOK Allowed
                          </Badge>
                        ) : (
                          <Badge className="bg-amber-500/10 text-amber-600 border-amber-500/20 text-[10px] gap-1 hover:bg-amber-500/20">
                            <Lock className="h-3 w-3" /> Platform Managed Only
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-center">
                        <div className="flex flex-wrap items-center justify-center gap-1">
                          <Badge className={p.is_active ? "bg-emerald-500/10 text-emerald-600 text-[10px]" : "text-[10px]"} variant={p.is_active ? "default" : "secondary"}>
                            {p.is_active ? "Active" : "Archived"}
                          </Badge>
                          <Badge variant={p.is_public ? "outline" : "secondary"} className="text-[10px]">
                            {p.is_public ? "Public" : "Private"}
                          </Badge>
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            onClick={() => {
                              setEditingPlan(p);
                              setModalOpen(true);
                            }}
                          >
                            <Edit className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            onClick={() => handleDelete(p.id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* CREATE / EDIT PLAN DIALOG */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingPlan?.id ? "Edit SaaS Plan" : "Create SaaS Plan"}</DialogTitle>
            <DialogDescription>
              Set one configured currency and its monthly and optional annual prices. No exchange rate is estimated.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-2 sm:grid-cols-2">
            <div className="space-y-1">
              <Label className="text-xs">Plan Title</Label>
              <Input
                placeholder="e.g. Growth Pro"
                value={editingPlan?.name || ""}
                onChange={(e) => setEditingPlan((prev) => prev ? { ...prev, name: e.target.value } : null)}
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Plan Identifier Code</Label>
              <Input
                placeholder="e.g. growth-pro"
                value={editingPlan?.code || ""}
                onChange={(e) => setEditingPlan((prev) => prev ? { ...prev, code: e.target.value } : null)}
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Currency</Label>
              <select
                value={editingPlan?.currency ?? "INR"}
                onChange={(event) => setEditingPlan((prev) => prev ? { ...prev, currency: event.target.value } : null)}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="INR">INR (₹)</option>
                <option value="USD">USD ($)</option>
              </select>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Monthly price ({editingPlan?.currency ?? "INR"})</Label>
              <Input
                type="number"
                min="0"
                step="0.01"
                value={((editingPlan?.monthly_price_cents ?? 0) / 100).toFixed(2)}
                onChange={(e) => setEditingPlan((prev) => prev ? { ...prev, monthly_price_cents: Math.max(0, Math.round((Number(e.target.value) || 0) * 100)) } : null)}
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Annual price ({editingPlan?.currency ?? "INR"}, optional)</Label>
              <Input
                type="number"
                min="0"
                step="0.01"
                value={((editingPlan?.annual_price_cents ?? 0) / 100).toFixed(2)}
                onChange={(e) => setEditingPlan((prev) => prev ? { ...prev, annual_price_cents: Math.max(0, Math.round((Number(e.target.value) || 0) * 100)) } : null)}
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="plan-included-minutes" className="text-xs">Minutes credited per purchase</Label>
              <Input
                id="plan-included-minutes"
                type="number"
                min={0}
                step={1}
                value={editingPlan?.included_minutes ?? 1000}
                onChange={(e) => setEditingPlan((prev) => prev ? { ...prev, included_minutes: parseInt(e.target.value) || 0 } : null)}
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="plan-max-calls" className="text-xs">Max Concurrent Voice Calls</Label>
              <Input
                id="plan-max-calls"
                type="number"
                min={0}
                step={1}
                value={editingPlan?.max_concurrent_calls ?? 5}
                onChange={(e) => setEditingPlan((prev) => prev ? { ...prev, max_concurrent_calls: Math.max(0, Math.trunc(e.target.valueAsNumber || 0)) } : null)}
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="plan-max-agents" className="text-xs">Max Voice Agents</Label>
              <Input id="plan-max-agents" type="number" min={0} step={1}
                value={editingPlan?.max_agents ?? 3}
                onChange={(e) => setEditingPlan((prev) => prev ? { ...prev, max_agents: Math.max(0, Math.trunc(e.target.valueAsNumber || 0)) } : null)} />
            </div>

            {([
              ["has_crm_access", "CRM access"],
              ["has_appointments_access", "Appointments access"],
              ["has_forms_access", "Forms access"],
              ["has_widget_access", "Widget access"],
              ["has_campaigns_access", "Campaigns access"],
            ] as const).map(([field, label]) => (
              <div key={field} className="flex items-center justify-between gap-3">
                <Label htmlFor={`plan-${field}`} className="text-xs">{label}</Label>
                <Switch id={`plan-${field}`} checked={editingPlan?.[field] ?? true}
                  onCheckedChange={(checked) => setEditingPlan((prev) => prev ? { ...prev, [field]: checked } : null)} />
              </div>
            ))}

            {/* BYOK TOGGLE */}
            <div className="col-span-2 p-3 rounded-lg border border-border/60 bg-muted/30 flex items-center justify-between">
              <div>
                <div className="text-xs font-semibold flex items-center gap-1.5">
                  <KeyRound className="h-3.5 w-3.5 text-primary" />
                  Allow User BYOK (Bring Your Own Key)
                </div>
                <div className="text-[11px] text-muted-foreground">
                  If switched OFF, users are strictly bound to platform-managed master keys and minute bundles.
                </div>
              </div>
              <Switch
                checked={editingPlan?.allow_user_byok ?? false}
                onCheckedChange={(checked) => setEditingPlan((prev) => prev ? { ...prev, allow_user_byok: checked } : null)}
              />
            </div>

            <div className="col-span-2 flex items-center justify-between pt-1">
              <Label className="text-xs">Active (available for purchase and public pricing)</Label>
              <Switch
                checked={editingPlan?.is_active ?? true}
                onCheckedChange={(checked) => setEditingPlan((prev) => prev ? { ...prev, is_active: checked } : null)}
              />
            </div>
            <div className="col-span-2 space-y-1">
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor="plan-public" className="text-xs">Show in public pricing and self-service checkout</Label>
                <Switch id="plan-public" checked={editingPlan?.is_public ?? true}
                  onCheckedChange={(checked) => setEditingPlan((prev) => prev ? { ...prev, is_public: checked } : null)} />
              </div>
              <p className="text-xs text-muted-foreground">
                Private active plans stay available for direct owner assignment but are hidden from the public catalog and checkout.
              </p>
            </div>
            <div className="col-span-2 space-y-2">
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor="plan-default" className="text-xs">Default fallback plan</Label>
                <Switch id="plan-default" checked={editingPlan?.is_default ?? false}
                  onCheckedChange={(checked) => setEditingPlan((prev) => prev ? { ...prev, is_default: checked } : null)} />
              </div>
              <p className="text-xs text-muted-foreground">
                Applies when an organization has no active assigned plan, including after expiry.
                Choosing this plan replaces the previous default. It must be active; this setting does not grant minutes.
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save Plan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
