"use client";

import {
  AlertOctagon,
  AlertTriangle,
  Ban,
  CheckCircle2,
  Edit,
  Loader2,
  Plus,
  RefreshCw,
  ShieldAlert,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { adminApi, BannedWord, FlaggedViolation } from "@/lib/kodewavesApi";

export default function AdminModerationPage() {
  const [bannedWords, setBannedWords] = useState<BannedWord[]>([]);
  const [violations, setViolations] = useState<FlaggedViolation[]>([]);
  const [loading, setLoading] = useState(true);

  // Add Banned Word Dialog
  const [modalOpen, setModalOpen] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [severity, setSeverity] = useState<"low" | "medium" | "high" | "critical">("high");
  const [action, setAction] = useState<"flag" | "terminate" | "alert_admin">("terminate");
  const [saving, setSaving] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [words, viols] = await Promise.all([
        adminApi.getBannedWords().catch(() => []),
        adminApi.getViolations().catch(() => []),
      ]);
      setBannedWords(words);
      setViolations(viols);
    } catch (err) {
      console.error("Failed to load moderation data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleAddKeyword = async () => {
    if (!keyword.trim()) return;
    setSaving(true);
    try {
      await adminApi.addBannedWord({
        keyword: keyword.trim().toLowerCase(),
        severity,
        action,
      });
      setModalOpen(false);
      setKeyword("");
      await fetchData();
    } catch (err: any) {
      alert(err.message || "Failed to add keyword");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteKeyword = async (id: number | string) => {
    if (!confirm("Are you sure you want to remove this keyword filter?")) return;
    try {
      await adminApi.deleteBannedWord(id);
      await fetchData();
    } catch (err: any) {
      alert(err.message || "Failed to delete keyword");
    }
  };

  const handleResolveViolation = async (id: number | string, isReviewed = true) => {
    try {
      await adminApi.resolveViolation(id, isReviewed);
      await fetchData();
    } catch (err: any) {
      alert(err.message || "Failed to update violation status");
    }
  };

  const handleDeleteViolation = async (id: number | string) => {
    if (!confirm("Delete this violation incident record?")) return;
    try {
      await adminApi.deleteViolation(id);
      await fetchData();
    } catch (err: any) {
      alert(err.message || "Failed to delete violation");
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Content Moderation & Safeguards</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Enforce real-time speech guardrails, ban illegal/abusive vocabulary, and inspect violation incidents.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            className="gap-2"
            onClick={() => {
              setKeyword("");
              setSeverity("high");
              setAction("terminate");
              setModalOpen(true);
            }}
          >
            <Plus className="h-4 w-4" /> Add Banned Keyword
          </Button>
          <Button variant="outline" size="sm" onClick={fetchData} disabled={loading} className="gap-2">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      <Tabs defaultValue="keywords" className="space-y-6">
        <TabsList className="grid w-full max-w-md grid-cols-2">
          <TabsTrigger value="keywords" className="gap-2">
            <Ban className="h-4 w-4" />
            Banned Words List ({bannedWords.length})
          </TabsTrigger>
          <TabsTrigger value="violations" className="gap-2">
            <AlertOctagon className="h-4 w-4" />
            Flagged Violations ({violations.length})
          </TabsTrigger>
        </TabsList>

        {/* TAB 1: BANNED WORDS */}
        <TabsContent value="keywords" className="space-y-6">
          <Card className="border-border/60">
            <CardHeader>
              <CardTitle className="text-base">Prohibited Lexicon Rules</CardTitle>
              <CardDescription>
                When any inbound or outbound transcript hits these keywords, the designated action is taken immediately.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="rounded-lg border border-border/60 overflow-hidden">
                <Table>
                  <TableHeader className="bg-muted/40">
                    <TableRow>
                      <TableHead className="text-xs">Keyword / Phrase</TableHead>
                      <TableHead className="text-xs text-center">Severity</TableHead>
                      <TableHead className="text-xs text-center">Action Triggered</TableHead>
                      <TableHead className="text-xs text-right">Created At</TableHead>
                      <TableHead className="text-xs text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {bannedWords.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="text-center py-8 text-sm text-muted-foreground">
                          No keywords banned. Click &quot;Add Banned Keyword&quot; to configure safety filters.
                        </TableCell>
                      </TableRow>
                    ) : (
                      bannedWords.map((w) => (
                        <TableRow key={w.id} className="hover:bg-muted/20">
                          <TableCell className="font-semibold text-xs font-mono">{w.keyword}</TableCell>
                          <TableCell className="text-center">
                            <Badge
                              variant={
                                w.severity === "critical"
                                  ? "destructive"
                                  : w.severity === "high"
                                  ? "outline"
                                  : "secondary"
                              }
                              className="text-[10px] uppercase font-semibold"
                            >
                              {w.severity}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-center">
                            <Badge
                              className={`text-[10px] font-semibold uppercase ${
                                w.action === "terminate"
                                  ? "bg-destructive/10 text-destructive border-destructive/20"
                                  : "bg-amber-500/10 text-amber-600 border-amber-500/20"
                              }`}
                            >
                              {w.action.replace("_", " ")}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs text-right text-muted-foreground">
                            {w.created_at ? new Date(w.created_at).toLocaleDateString() : "—"}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-destructive hover:text-destructive"
                              onClick={() => handleDeleteKeyword(w.id)}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
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

        {/* TAB 2: VIOLATIONS LOG */}
        <TabsContent value="violations" className="space-y-6">
          <Card className="border-border/60">
            <CardHeader>
              <CardTitle className="text-base">Violation Incidents & Interventions</CardTitle>
              <CardDescription>
                Audit history of active calls that triggered speech moderation filters.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="rounded-lg border border-border/60 overflow-hidden">
                <Table>
                  <TableHeader className="bg-muted/40">
                    <TableRow>
                      <TableHead className="text-xs">Run ID</TableHead>
                      <TableHead className="text-xs">Organization ID</TableHead>
                      <TableHead className="text-xs">Violation Type</TableHead>
                      <TableHead className="text-xs">Matched Text</TableHead>
                      <TableHead className="text-xs">Action Taken</TableHead>
                      <TableHead className="text-xs">Status</TableHead>
                      <TableHead className="text-xs">Timestamp</TableHead>
                      <TableHead className="text-xs text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {violations.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={8} className="text-center py-8 text-sm text-muted-foreground">
                          Zero safety violations recorded. Platform is healthy.
                        </TableCell>
                      </TableRow>
                    ) : (
                      violations.map((v) => (
                        <TableRow key={v.id} className="hover:bg-muted/20">
                          <TableCell className="font-mono text-xs font-semibold">#{v.workflow_run_id}</TableCell>
                          <TableCell className="text-xs">Org #{v.organization_id}</TableCell>
                          <TableCell>
                            <Badge variant="outline" className="text-[10px] text-destructive border-destructive/30">
                              {v.violation_type}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs font-mono text-destructive">{v.matched_text}</TableCell>
                          <TableCell className="text-xs font-semibold">{v.action_taken}</TableCell>
                          <TableCell>
                            {v.is_reviewed ? (
                              <Badge variant="secondary" className="text-[10px] bg-emerald-500/10 text-emerald-600 border-emerald-500/20">
                                Resolved
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="text-[10px] text-amber-500 border-amber-500/30">
                                Pending
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {v.created_at ? new Date(v.created_at).toLocaleString() : "—"}
                          </TableCell>
                          <TableCell className="text-xs text-right">
                            <div className="flex items-center justify-end gap-1.5">
                              {!v.is_reviewed ? (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 px-2 text-xs text-emerald-600 hover:text-emerald-700 hover:bg-emerald-500/10"
                                  onClick={() => handleResolveViolation(v.id, true)}
                                  title="Mark as Resolved"
                                >
                                  <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Resolve
                                </Button>
                              ) : (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 px-2 text-xs text-muted-foreground hover:bg-muted/40"
                                  onClick={() => handleResolveViolation(v.id, false)}
                                  title="Reopen incident"
                                >
                                  Reopen
                                </Button>
                              )}
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                                onClick={() => handleDeleteViolation(v.id)}
                                title="Delete record"
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
        </TabsContent>
      </Tabs>

      {/* ADD KEYWORD DIALOG */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add Banned Keyword or Phrase</DialogTitle>
            <DialogDescription>
              Define the prohibited speech token and what action the platform must take upon detection.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label className="text-xs">Keyword or Phrase</Label>
              <Input
                placeholder="e.g. credit card cvv, bank account number"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Severity</Label>
              <Select value={severity} onValueChange={(val: any) => setSeverity(val)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">Low (Monitoring only)</SelectItem>
                  <SelectItem value="medium">Medium (Audit flag)</SelectItem>
                  <SelectItem value="high">High (Warning & Action)</SelectItem>
                  <SelectItem value="critical">Critical (Immediate Stop)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Action on Detection</Label>
              <Select value={action} onValueChange={(val: any) => setAction(val)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="terminate">Terminate Call Immediately</SelectItem>
                  <SelectItem value="flag">Flag & Record Incident</SelectItem>
                  <SelectItem value="alert_admin">Alert Admin via Email</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={handleAddKeyword} disabled={saving || !keyword.trim()}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save Keyword Filter
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
