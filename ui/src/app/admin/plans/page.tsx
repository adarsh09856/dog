"use client";

import {
  Check,
  Edit,
  FileSpreadsheet,
  KeyRound,
  Layers,
  Loader2,
  Lock,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  Unlock,
} from "lucide-react";
import React, { useEffect, useState } from "react";

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
import { Textarea } from "@/components/ui/textarea";
import { adminApi, SaaSPlan } from "@/lib/kodewavesApi";

export default function AdminPlansPage() {
  const [plans, setPlans] = useState<SaaSPlan[]>([]);
  const [loading, setLoading] = useState(true);

  // Modal
  const [modalOpen, setModalOpen] = useState(false);
  const [editingPlan, setEditingPlan] = useState<Partial<SaaSPlan> | null>(null);
  const [saving, setSaving] = useState(false);

  const fetchPlans = async () => {
    setLoading(true);
    try {
      const data = await adminApi.getPlans();
      setPlans(data);
    } catch (err) {
      console.error("Failed to load plans:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPlans();
  }, []);

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
    } catch (err: any) {
      alert(err.message || "Failed to save SaaS plan");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number | string) => {
    if (!confirm("Are you sure you want to delete this subscription plan?")) return;
    try {
      await adminApi.deletePlan(id);
      await fetchPlans();
    } catch (err: any) {
      alert(err.message || "Failed to delete plan");
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">SaaS Subscription Plans</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure recurring tiers, voice minute quotas, concurrency limits, and enforce sovereign BYOK restrictions.
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
                monthly_price_inr: 4999,
                monthly_price_usd: 59,
                included_minutes: 1000,
                overage_rate_per_minute: 2.0,
                max_concurrent_calls: 5,
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
                  <TableHead className="text-xs text-right">Price (₹ INR / $ USD)</TableHead>
                  <TableHead className="text-xs text-right">Included Mins</TableHead>
                  <TableHead className="text-xs text-right">Overage (₹/m)</TableHead>
                  <TableHead className="text-xs text-center">Concurrency</TableHead>
                  <TableHead className="text-xs text-center">BYOK Policy</TableHead>
                  <TableHead className="text-xs text-center">Status</TableHead>
                  <TableHead className="text-xs text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {plans.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={9} className="text-center py-8 text-sm text-muted-foreground">
                      No plans created yet. Click &quot;Create Plan&quot; to build your first tier.
                    </TableCell>
                  </TableRow>
                ) : (
                  plans.map((p) => (
                    <TableRow key={p.id} className="hover:bg-muted/20">
                      <TableCell className="font-semibold text-xs">{p.name}</TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">{p.code}</TableCell>
                      <TableCell className="text-xs text-right font-mono font-medium">
                        ₹{p.monthly_price_inr.toLocaleString()} / ${p.monthly_price_usd}
                      </TableCell>
                      <TableCell className="text-xs text-right font-mono font-bold text-emerald-600 dark:text-emerald-400">
                        {p.included_minutes.toLocaleString()} mins
                      </TableCell>
                      <TableCell className="text-xs text-right font-mono">₹{p.overage_rate_per_minute.toFixed(2)}</TableCell>
                      <TableCell className="text-center font-mono text-xs">{p.max_concurrent_calls} calls</TableCell>
                      <TableCell className="text-center">
                        {p.allow_user_byok ? (
                          <Badge variant="outline" className="text-[10px] text-indigo-500 border-indigo-500/30 gap-1">
                            <Unlock className="h-3 w-3" /> BYOK Allowed
                          </Badge>
                        ) : (
                          <Badge className="bg-amber-500/10 text-amber-600 border-amber-500/20 text-[10px] gap-1 hover:bg-amber-500/20">
                            <Lock className="h-3 w-3" /> Platform Managed Only
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-center">
                        {p.is_active ? (
                          <Badge className="bg-emerald-500/10 text-emerald-600 text-[10px]">
                            Active
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="text-[10px]">
                            Archived
                          </Badge>
                        )}
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
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingPlan?.id ? "Edit SaaS Plan" : "Create SaaS Subscription Plan"}</DialogTitle>
            <DialogDescription>
              Set pricing in INR and USD, allocate monthly minutes, and choose BYOK permissions.
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
              <Label className="text-xs">Monthly Price (₹ INR)</Label>
              <Input
                type="number"
                value={editingPlan?.monthly_price_inr ?? 0}
                onChange={(e) => setEditingPlan((prev) => prev ? { ...prev, monthly_price_inr: parseFloat(e.target.value) || 0 } : null)}
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Monthly Price ($ USD)</Label>
              <Input
                type="number"
                value={editingPlan?.monthly_price_usd ?? 0}
                onChange={(e) => setEditingPlan((prev) => prev ? { ...prev, monthly_price_usd: parseFloat(e.target.value) || 0 } : null)}
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Included Monthly Minutes</Label>
              <Input
                type="number"
                value={editingPlan?.included_minutes ?? 1000}
                onChange={(e) => setEditingPlan((prev) => prev ? { ...prev, included_minutes: parseInt(e.target.value) || 0 } : null)}
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Overage Rate (₹/min)</Label>
              <Input
                type="number"
                step="0.1"
                value={editingPlan?.overage_rate_per_minute ?? 2.0}
                onChange={(e) => setEditingPlan((prev) => prev ? { ...prev, overage_rate_per_minute: parseFloat(e.target.value) || 0 } : null)}
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Max Concurrent Voice Calls</Label>
              <Input
                type="number"
                value={editingPlan?.max_concurrent_calls ?? 5}
                onChange={(e) => setEditingPlan((prev) => prev ? { ...prev, max_concurrent_calls: parseInt(e.target.value) || 1 } : null)}
              />
            </div>

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
              <Label className="text-xs">Active & Listed in Pricing View</Label>
              <Switch
                checked={editingPlan?.is_active ?? true}
                onCheckedChange={(checked) => setEditingPlan((prev) => prev ? { ...prev, is_active: checked } : null)}
              />
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
