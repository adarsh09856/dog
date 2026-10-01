"use client";

import {
  FileText,
  Filter,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import React, { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { adminApi, AuditLogItem } from "@/lib/kodewavesApi";

export default function AdminAuditLogsPage() {
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const data = await adminApi.getAuditLogs();
      setLogs(data);
    } catch (err) {
      console.error("Failed to load audit logs:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const filteredLogs = logs.filter(
    (l) =>
      (l.action || "").toLowerCase().includes(search.toLowerCase()) ||
      (l.target_resource || "").toLowerCase().includes(search.toLowerCase()) ||
      (l.user_email && l.user_email.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">System Audit Trail</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Immutable log of all administrative actions, key rotations, credit adjustments, and kill-switch executions.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative w-64">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search actions or admin..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 h-9 text-xs"
            />
          </div>
          <Button variant="outline" size="sm" onClick={fetchLogs} disabled={loading} className="gap-2">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            <span>Audit Events ({filteredLogs.length})</span>
            <Badge variant="secondary" className="text-xs gap-1">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" /> Tamper-Proof
            </Badge>
          </CardTitle>
          <CardDescription>
            Records every high-privilege mutation performed within the Kodewaves sovereign control plane.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-border/60 overflow-hidden">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow>
                  <TableHead className="text-xs">Timestamp</TableHead>
                  <TableHead className="text-xs">Admin / Actor</TableHead>
                  <TableHead className="text-xs">Action</TableHead>
                  <TableHead className="text-xs">Target Resource</TableHead>
                  <TableHead className="text-xs">Payload Details</TableHead>
                  <TableHead className="text-xs text-right">IP Address</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredLogs.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-sm text-muted-foreground">
                      No audit events recorded yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredLogs.map((l) => (
                    <TableRow key={l.id} className="hover:bg-muted/20">
                      <TableCell className="text-xs text-muted-foreground font-mono">
                        {l.created_at ? new Date(l.created_at).toLocaleString() : "—"}
                      </TableCell>
                      <TableCell className="text-xs font-medium">{l.user_email || "System"}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-[10px] font-mono uppercase font-semibold">
                          {l.action}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs font-semibold">{l.target_resource}</TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground max-w-xs truncate">
                        {l.details ? JSON.stringify(l.details) : "—"}
                      </TableCell>
                      <TableCell className="text-xs text-right font-mono text-muted-foreground">
                        {l.ip_address || "127.0.0.1"}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
