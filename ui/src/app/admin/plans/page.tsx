"use client";

import {
  Check,
  CircleX,
  Edit,
  Globe,
  KeyRound,
  Layers,
  Loader2,
  Lock,
  Plus,
  RefreshCw,
  Trash2,
  Unlock,
  Users,
} from "lucide-react";
import React, { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { adminApi, SaaSPlan } from "@/lib/kodewavesApi";

import admin from "../AdminWorkspace.module.css";
import styles from "./PlansWorkspace.module.css";

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

  const activeCount = plans.filter((plan) => plan.is_active).length;
  const publicCount = plans.filter((plan) => plan.is_active && plan.is_public).length;
  const managedKeyCount = plans.filter((plan) => !plan.allow_user_byok).length;

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
    <div className={`${admin.surface} ${styles.surface}`} data-area="COMMERCE / PLANS">
      {/* Header */}
      <div className={admin.hero}>
        <div>
          <span className={admin.kicker}>COMMERCE / PLANS</span>
          <h1 className={admin.title}>Plan governance</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Set the entitlements, capacity, pricing, and publication rules that every organization receives. Plans use manual renewal; minutes are granted once per purchase.
          </p>
        </div>
        <div className={`${styles.heroActions} flex w-full flex-wrap items-center gap-2 sm:w-auto sm:justify-end`}>
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

      {error && <p role="alert" className={styles.error}>{error} Use Refresh to retry.</p>}

      <section className={styles.portfolio} aria-label="Plan portfolio summary">
        {[
          { label: "Defined tiers", value: loading ? "—" : plans.length, icon: Layers },
          { label: "Active for assignment", value: loading ? "—" : activeCount, icon: Users },
          { label: "Public catalog", value: loading ? "—" : publicCount, icon: Globe },
          { label: "Platform-managed keys", value: loading ? "—" : managedKeyCount, icon: Lock },
        ].map(({ label, value, icon: Icon }) => (
          <div className={styles.portfolioItem} key={label}>
            <span className={styles.portfolioIcon}><Icon size={17} aria-hidden="true" /></span>
            <div><p className={styles.portfolioLabel}>{label}</p><p className={styles.portfolioValue}>{value}</p></div>
          </div>
        ))}
      </section>

      <section className={styles.catalog} aria-labelledby="available-plans-heading">
        <div className={styles.catalogHeader}>
          <div>
            <h2 id="available-plans-heading">Available tiers</h2>
            <p>Owner-defined limits and feature grants are enforced for organizations assigned to each plan.</p>
          </div>
          <span className={styles.catalogCount}>{loading ? "Loading catalog" : `${plans.length} ${plans.length === 1 ? "tier" : "tiers"}`}</span>
        </div>
        {loading ? (
          <div role="status" className={styles.empty}><Loader2 className="h-5 w-5 animate-spin text-primary" /><p>Loading plan catalog…</p></div>
        ) : error ? (
          <div className={styles.empty} role="status"><p>Plan data is unavailable. Refresh to retry.</p></div>
        ) : plans.length === 0 ? (
          <div className={styles.empty}>
            <span className={styles.emptyIcon}><Layers size={20} /></span>
            <h3>No plans created yet</h3>
            <p>Build the first tier with a plan code, quotas, feature access, and billing terms.</p>
            <Button onClick={() => {
              setEditingPlan({
                name: "New Tier", code: "new-tier", monthly_price_cents: 499900, annual_price_cents: 0,
                currency: "INR", included_minutes: 1000, max_concurrent_calls: 5, max_agents: 3,
                has_crm_access: true, has_appointments_access: true, has_forms_access: true,
                has_widget_access: true, has_campaigns_access: true, allow_user_byok: false,
                is_active: true, is_public: true,
              });
              setModalOpen(true);
            }}>Create first plan</Button>
          </div>
        ) : (
          <div className={styles.planGrid}>
            {plans.map((p) => {
              const features = [
                ["CRM", p.has_crm_access],
                ["Appointments", p.has_appointments_access],
                ["Voice forms", p.has_forms_access],
                ["Web widgets", p.has_widget_access],
                ["Campaigns", p.has_campaigns_access],
              ] as const;
              return (
                <Card key={p.id} className={`${styles.planCard} ${p.is_default ? styles.defaultPlan : ""}`}>
                  <div className={styles.planHeader}>
                    <div className={styles.planIdentity}>
                      <span className={styles.planIcon}><Layers size={18} aria-hidden="true" /></span>
                      <div className="min-w-0">
                        <h3 className={styles.planName}>{p.name}</h3>
                        <p className={styles.planCode}>{p.code}</p>
                      </div>
                    </div>
                    <div className={styles.planBadges}>
                      {p.is_default && <Badge variant="outline">Default fallback</Badge>}
                      <Badge variant={p.is_active ? "default" : "secondary"}>{p.is_active ? "Active" : "Archived"}</Badge>
                      <Badge variant={p.is_public ? "outline" : "secondary"}>{p.is_public ? "Public" : "Private"}</Badge>
                    </div>
                  </div>
                  <CardContent className={styles.planBody}>
                    <div className={styles.priceRail} aria-label={`${p.name} prices`}>
                      <div className={styles.priceCell}><span className={styles.priceLabel}>Monthly · 30 days</span><p className={styles.priceValue}>{formatMoney(p.monthly_price_cents / 100, p.currency)}</p></div>
                      <div className={styles.priceCell}><span className={styles.priceLabel}>Annual · 365 days</span><p className={styles.priceValue}>{p.annual_price_cents > 0 ? formatMoney(p.annual_price_cents / 100, p.currency) : "Not set"}</p></div>
                    </div>
                    <div className={styles.limitGrid} aria-label={`${p.name} plan limits`}>
                      <div className={styles.limitCell}><strong className={styles.limitValue}>{p.included_minutes.toLocaleString()}</strong><span className={styles.limitLabel}>Minutes / purchase</span></div>
                      <div className={styles.limitCell}><strong className={styles.limitValue}>{p.max_concurrent_calls}</strong><span className={styles.limitLabel}>Concurrent calls</span></div>
                      <div className={styles.limitCell}><strong className={styles.limitValue}>{p.max_agents ?? 0}</strong><span className={styles.limitLabel}>Voice agents</span></div>
                    </div>
                    <div>
                      <div className={styles.ruleHeading}><span>Enforced feature access</span><span>{features.filter(([, enabled]) => enabled).length}/{features.length}</span></div>
                      <div className={styles.featureGrid}>
                        {features.map(([label, enabled]) => (
                          <span key={label} className={`${styles.feature} ${enabled ? styles.featureEnabled : styles.featureDisabled}`}>
                            {enabled ? <Check size={13} aria-hidden="true" /> : <CircleX size={13} aria-hidden="true" />}{label}
                          </span>
                        ))}
                      </div>
                      <div className={styles.byokLine}>
                        {p.allow_user_byok ? <Unlock size={13} className="text-primary" aria-hidden="true" /> : <Lock size={13} className="text-amber-600" aria-hidden="true" />}
                        <span>{p.allow_user_byok ? "Customer API keys allowed" : "Platform-managed keys required"}</span>
                      </div>
                    </div>
                  </CardContent>
                  <div className={styles.cardActions}>
                    <Button variant="outline" size="sm" aria-label={`Edit ${p.name}`} onClick={() => { setEditingPlan(p); setModalOpen(true); }}>
                      <Edit className="mr-1.5 h-3.5 w-3.5" /> Edit plan
                    </Button>
                    <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive" aria-label={`Delete ${p.name}`} onClick={() => handleDelete(p.id)}>
                      <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Delete
                    </Button>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </section>

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
