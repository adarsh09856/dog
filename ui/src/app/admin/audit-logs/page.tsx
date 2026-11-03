"use client";

import admin from "../AdminWorkspace.module.css";

import { Download, RefreshCw, Search, ShieldCheck } from "lucide-react";
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
import { useClientBranding } from "@/context/ClientBrandingContext";
import { adminApi, AuditLogItem } from "@/lib/kodewavesApi";

const csvCell = (value: unknown) => {
  const text = value == null ? "" : String(value);
  const formulaLike = /^[\u0000-\u0020]*[=+\-@]/.test(text) || /^[\t\r\n]/.test(text);
  const safeText = formulaLike ? `'${text}` : text;
  return `"${safeText.replace(/"/g, '""')}"`;
};

export function buildAuditLogsCsv(logs: AuditLogItem[]) {
  const headers = ["Timestamp", "Admin / Actor", "Action", "Target Resource", "Payload Details", "IP Address"];
  const rows = logs.map((log) => {
    const timestamp = log.created_at
      ? (() => {
          const parsed = new Date(log.created_at);
          return Number.isNaN(parsed.getTime()) ? log.created_at : parsed.toISOString();
        })()
      : "";
    return [
      timestamp,
      log.user_email || "System",
      log.action,
      log.target_resource,
      log.details ? JSON.stringify(log.details) : "",
      log.ip_address || "Unavailable",
    ];
  });
  return [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
}

export default function AdminAuditLogsPage() {
  const { company_name } = useClientBranding();
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await adminApi.getAuditLogs();
      setLogs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load audit logs");
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

  const exportCsv = () => {
    const csvContent = buildAuditLogsCsv(filteredLogs);
    const encodedUri = `data:text/csv;charset=utf-8,${encodeURIComponent(csvContent)}`;
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `kodewaves_audit_logs_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className={admin.surface} data-area="SECURITY / AUDIT">
      {/* Header */}
      <div className={admin.hero}>
        <div>
          <span className={admin.kicker}>SECURITY / AUDIT</span>
          <h1 className={admin.title}>System Audit Trail</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Immutable log of all administrative actions, key rotations, credit adjustments, and kill-switch executions.
          </p>
        </div>
        <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:justify-end">
          <div className="relative w-64">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search actions or admin..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 h-9 text-xs"
            />
          </div>
          <Button variant="outline" size="sm" onClick={exportCsv} disabled={filteredLogs.length === 0} className="gap-2">
            <Download className="h-3.5 w-3.5" />
            Export CSV
          </Button>
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
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" /> Audit trail
            </Badge>
          </CardTitle>
          <CardDescription>
            Records every high-privilege mutation performed within the {company_name} control plane.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error && <p role="alert" className="mb-3 text-sm text-destructive">{error} Use Refresh to retry.</p>}
          <div className="overflow-x-auto rounded-xl border border-border/60">
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
                      {loading ? 'Loading audit events…' : error ? 'Audit events could not be loaded.' : 'No audit events recorded yet.'}
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
                        {l.ip_address || "Unavailable"}
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
