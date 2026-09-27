"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  PhoneCall,
  PhoneOff,
  Radio,
  RefreshCw,
  ShieldAlert,
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
import { adminApi, LiveCallItem } from "@/lib/kodewavesApi";

export default function AdminMonitoringPage() {
  const [calls, setCalls] = useState<LiveCallItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [killingId, setKillingId] = useState<number | null>(null);

  const fetchCalls = async () => {
    try {
      const data = await adminApi.getLiveCalls();
      setCalls(data);
    } catch (err) {
      console.error("Failed to load live calls:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCalls();
    const interval = setInterval(fetchCalls, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleKillCall = async (runId: number) => {
    if (!confirm(`EMERGENCY ACTION: Immediately terminate active voice call #${runId}?`)) return;
    setKillingId(runId);
    try {
      await adminApi.killCall(runId, "Admin emergency kill switch triggered");
      await fetchCalls();
    } catch (err: any) {
      alert(err.message || "Failed to terminate call");
    } finally {
      setKillingId(null);
    }
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Real-Time Voice Call Telemetry</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Live monitoring feed of in-flight SIP trunks, WebRTC sessions, and emergency termination control.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="outline" className="px-3 py-1 bg-emerald-500/10 text-emerald-600 border-emerald-500/20 text-xs gap-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            Live Polling (3s)
          </Badge>
          <Button variant="outline" size="sm" onClick={fetchCalls} className="gap-2">
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Radio className="h-5 w-5 text-emerald-500 animate-pulse" />
              <span>In-Flight Active Sessions ({calls.length})</span>
            </div>
            <Badge variant="destructive" className="text-xs gap-1">
              <ShieldAlert className="h-3.5 w-3.5" /> Admin Kill-Switch Enabled
            </Badge>
          </CardTitle>
          <CardDescription>
            Calls are streaming audio through sovereign Pipecat worker instances. Pressing &quot;Kill Call&quot; immediately sends a SIP BYE / WebRTC close.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-border/60 overflow-hidden">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow>
                  <TableHead className="text-xs">Run ID</TableHead>
                  <TableHead className="text-xs">Agent Name</TableHead>
                  <TableHead className="text-xs">Organization / User</TableHead>
                  <TableHead className="text-xs">AI Provider</TableHead>
                  <TableHead className="text-xs">Telecom Carrier</TableHead>
                  <TableHead className="text-xs">Duration</TableHead>
                  <TableHead className="text-xs text-center">Status</TableHead>
                  <TableHead className="text-xs text-right">Emergency Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {calls.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center py-12 text-sm text-muted-foreground">
                      <div className="flex flex-col items-center justify-center gap-2">
                        <CheckCircle2 className="h-8 w-8 text-emerald-500/60" />
                        <span>No voice calls currently active on the platform.</span>
                        <span className="text-xs text-muted-foreground">System is idle and ready for incoming/outgoing traffic.</span>
                      </div>
                    </TableCell>
                  </TableRow>
                ) : (
                  calls.map((c) => (
                    <TableRow key={c.run_id} className="hover:bg-muted/20">
                      <TableCell className="font-mono text-xs font-semibold">#{c.run_id}</TableCell>
                      <TableCell className="text-xs font-medium">{c.agent_name}</TableCell>
                      <TableCell className="text-xs">
                        <div className="font-medium">{c.organization_name || "Direct Tenant"}</div>
                        {c.user_email && <div className="text-[11px] text-muted-foreground">{c.user_email}</div>}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-[10px] uppercase font-semibold">
                          {c.provider}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs font-semibold uppercase">{c.telecom_carrier}</TableCell>
                      <TableCell className="font-mono text-xs font-bold text-primary flex items-center gap-1">
                        <Clock className="h-3 w-3" /> {formatDuration(c.duration_seconds)}
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge className="bg-emerald-500/10 text-emerald-600 text-[10px] gap-1 hover:bg-emerald-500/20">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                          Streaming
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="destructive"
                          size="sm"
                          className="h-7 text-xs gap-1 font-semibold"
                          disabled={killingId === c.run_id}
                          onClick={() => handleKillCall(c.run_id)}
                        >
                          <PhoneOff className="h-3.5 w-3.5" />
                          {killingId === c.run_id ? "Terminating..." : "Kill Call"}
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
    </div>
  );
}
