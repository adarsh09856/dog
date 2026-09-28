"use client";

import {
  Coins,
  Edit,
  Flame,
  Loader2,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
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
import { adminApi, CreditPackage } from "@/lib/kodewavesApi";

export default function AdminCreditPackagesPage() {
  const [packages, setPackages] = useState<CreditPackage[]>([]);
  const [loading, setLoading] = useState(true);

  // Modal
  const [modalOpen, setModalOpen] = useState(false);
  const [editingPackage, setEditingPackage] = useState<Partial<CreditPackage> | null>(null);
  const [saving, setSaving] = useState(false);

  const fetchPackages = async () => {
    setLoading(true);
    try {
      const data = await adminApi.getCreditPackages();
      setPackages(data);
    } catch (err) {
      console.error("Failed to load credit packages:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPackages();
  }, []);

  const handleSave = async () => {
    if (!editingPackage || !editingPackage.name) return;
    setSaving(true);
    try {
      if (editingPackage.id) {
        await adminApi.updateCreditPackage(editingPackage.id, editingPackage);
      } else {
        await adminApi.createCreditPackage(editingPackage);
      }
      setModalOpen(false);
      setEditingPackage(null);
      await fetchPackages();
    } catch (err: any) {
      alert(err.message || "Failed to save credit bundle");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number | string) => {
    if (!confirm("Are you sure you want to delete this credit bundle?")) return;
    try {
      await adminApi.deleteCreditPackage(id);
      await fetchPackages();
    } catch (err: any) {
      alert(err.message || "Failed to delete package");
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Voice Minute Bundles (Top-ups)</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Create on-demand minute packages with bonus credits and sovereign INR/USD retail rates.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            className="gap-2"
            onClick={() => {
              setEditingPackage({
                name: "1,000 Minutes Pack",
                minutes: 1000,
                bonus_minutes: 100,
                price_inr: 1999,
                price_usd: 25,
                is_popular: false,
                is_active: true,
              });
              setModalOpen(true);
            }}
          >
            <Plus className="h-4 w-4" /> Create Bundle
          </Button>
          <Button variant="outline" size="sm" onClick={fetchPackages} disabled={loading} className="gap-2">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            <span>Available Top-Up Bundles ({packages.length})</span>
            <Badge variant="secondary" className="text-xs">
              Immediate Local Wallet Credit
            </Badge>
          </CardTitle>
          <CardDescription>
            Tenants purchase these bundles in their Sovereign Billing tab to top up their running minute balances.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-border/60 overflow-hidden">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow>
                  <TableHead className="text-xs">Bundle Name</TableHead>
                  <TableHead className="text-xs text-right">Base Minutes</TableHead>
                  <TableHead className="text-xs text-right">Bonus Mins</TableHead>
                  <TableHead className="text-xs text-right font-bold">Total Delivered</TableHead>
                  <TableHead className="text-xs text-right">Price (₹ INR / $ USD)</TableHead>
                  <TableHead className="text-xs text-center">Badge</TableHead>
                  <TableHead className="text-xs text-center">Status</TableHead>
                  <TableHead className="text-xs text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {packages.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center py-8 text-sm text-muted-foreground">
                      No top-up bundles created yet. Click &quot;Create Bundle&quot; to add your first.
                    </TableCell>
                  </TableRow>
                ) : (
                  packages.map((pkg) => (
                    <TableRow key={pkg.id} className="hover:bg-muted/20">
                      <TableCell className="font-semibold text-xs">{pkg.name}</TableCell>
                      <TableCell className="text-xs text-right font-mono">{pkg.minutes.toLocaleString()} m</TableCell>
                      <TableCell className="text-xs text-right font-mono text-emerald-500">
                        {pkg.bonus_minutes > 0 ? `+${pkg.bonus_minutes} m` : "—"}
                      </TableCell>
                      <TableCell className="text-xs text-right font-mono font-bold text-emerald-600 dark:text-emerald-400">
                        {(pkg.minutes + pkg.bonus_minutes).toLocaleString()} mins
                      </TableCell>
                      <TableCell className="text-xs text-right font-mono font-medium">
                        ₹{pkg.price_inr.toLocaleString()} / ${pkg.price_usd}
                      </TableCell>
                      <TableCell className="text-center">
                        {pkg.is_popular ? (
                          <Badge className="bg-amber-500/10 text-amber-600 border-amber-500/20 text-[10px] gap-1">
                            <Flame className="h-3 w-3 fill-amber-500 text-amber-500" /> Popular
                          </Badge>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell className="text-center">
                        {pkg.is_active ? (
                          <Badge className="bg-emerald-500/10 text-emerald-600 text-[10px]">
                            Active
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="text-[10px]">
                            Hidden
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
                              setEditingPackage(pkg);
                              setModalOpen(true);
                            }}
                          >
                            <Edit className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            onClick={() => handleDelete(pkg.id)}
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

      {/* MODAL */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingPackage?.id ? "Edit Credit Bundle" : "Create Minute Bundle"}</DialogTitle>
            <DialogDescription>
              Configure package name, minute count, bonus incentive, and pricing.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label className="text-xs">Bundle Name</Label>
              <Input
                placeholder="e.g. 5,000 Minutes Growth Pack"
                value={editingPackage?.name || ""}
                onChange={(e) => setEditingPackage((prev) => prev ? { ...prev, name: e.target.value } : null)}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Base Minutes</Label>
                <Input
                  type="number"
                  value={editingPackage?.minutes ?? 1000}
                  onChange={(e) => setEditingPackage((prev) => prev ? { ...prev, minutes: parseInt(e.target.value) || 0 } : null)}
                />
              </div>

              <div className="space-y-1">
                <Label className="text-xs">Bonus Minutes</Label>
                <Input
                  type="number"
                  value={editingPackage?.bonus_minutes ?? 0}
                  onChange={(e) => setEditingPackage((prev) => prev ? { ...prev, bonus_minutes: parseInt(e.target.value) || 0 } : null)}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Price (₹ INR)</Label>
                <Input
                  type="number"
                  value={editingPackage?.price_inr ?? 0}
                  onChange={(e) => setEditingPackage((prev) => prev ? { ...prev, price_inr: parseFloat(e.target.value) || 0 } : null)}
                />
              </div>

              <div className="space-y-1">
                <Label className="text-xs">Price ($ USD)</Label>
                <Input
                  type="number"
                  value={editingPackage?.price_usd ?? 0}
                  onChange={(e) => setEditingPackage((prev) => prev ? { ...prev, price_usd: parseFloat(e.target.value) || 0 } : null)}
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-1">
              <Label className="text-xs">Highlight with &quot;Popular&quot; Tag</Label>
              <Switch
                checked={editingPackage?.is_popular ?? false}
                onCheckedChange={(checked) => setEditingPackage((prev) => prev ? { ...prev, is_popular: checked } : null)}
              />
            </div>

            <div className="flex items-center justify-between">
              <Label className="text-xs">Visible in Billing Store</Label>
              <Switch
                checked={editingPackage?.is_active ?? true}
                onCheckedChange={(checked) => setEditingPackage((prev) => prev ? { ...prev, is_active: checked } : null)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save Bundle
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
