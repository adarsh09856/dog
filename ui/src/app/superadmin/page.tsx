"use client";

import {
  AlertTriangle,
  ArrowUpRight,
  Clock,
  Coins,
  Cpu,
  FileCheck2,
  FileSpreadsheet,
  KeyRound,
  PackageCheck,
  Palette,
  Radio,
  RefreshCw,
  ScrollText,
  ShieldAlert,
  TrendingUp,
  Users,
} from "lucide-react";
import Link from "next/link";
import React, { useEffect, useState } from "react";

import panel from "@/components/layout/PanelWorkspace.module.css";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { adminApi, MonitoringStats } from "@/lib/kodewavesApi";

import admin from "./AdminWorkspace.module.css";

const CONTROL_GROUPS = [
  {
    title: "Accounts & commercial",
    description: "Manage customer access, entitlements, licensed deployments and usage products.",
    items: [
      { href: "/superadmin/users", title: "Accounts & organizations", detail: "Provision users, assign plans and features, manage access and wallet balances", icon: Users },
      { href: "/superadmin/plans", title: "SaaS plans", detail: "Set included features, usage limits, pricing and plan availability", icon: FileSpreadsheet },
      { href: "/superadmin/client-installations", title: "Client installations & releases", detail: "Issue licenses, approve bindings, review integrity and control updates", icon: PackageCheck },
      { href: "/superadmin/credit-packages", title: "Credit bundles", detail: "Configure purchasable and grantable usage packages", icon: Coins },
    ],
  },
  {
    title: "AI & platform configuration",
    description: "Control the shared model catalog, provider access and Kodewaves platform identity.",
    items: [
      { href: "/superadmin/models", title: "Models & provider credentials", detail: "Configure provider keys, model availability and catalog pricing", icon: Cpu },
      { href: "/superadmin/settings", title: "Platform identity & public branding", detail: "Set the platform name, logo, theme, support and public contact details", icon: Palette },
      { href: "/superadmin/settings#settings-local-ai", title: "Self-hosted voice stack", detail: "Configure local LLM, STT and TTS services and concurrency", icon: KeyRound },
      { href: "/superadmin/settings#settings-email", title: "Email & payment connections", detail: "Configure delivery, payment providers and run connection checks", icon: FileCheck2 },
    ],
  },
  {
    title: "Operations & trust",
    description: "Monitor live activity, investigate outcomes and keep a reviewable admin record.",
    items: [
      { href: "/superadmin/monitoring", title: "Live operations", detail: "Inspect active calls, process health and terminate a call when required", icon: Radio },
      { href: "/superadmin/runs", title: "Global call history", detail: "Review workflow runs, outcomes and conversation records", icon: Clock },
      { href: "/superadmin/moderation", title: "Content moderation", detail: "Review policy violations and manage blocked terms", icon: ShieldAlert },
      { href: "/superadmin/audit-logs", title: "Audit trail", detail: "Inspect platform owner actions and administrative changes", icon: ScrollText },
    ],
  },
];

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<MonitoringStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = async () => {
    setLoading(true);
    try {
      const data = await adminApi.getStats();
      setStats(data);
      setError(null);
    } catch (err: unknown) {
      console.error("Failed to load admin stats:", err);
      setError(err instanceof Error ? err.message : "Failed to load live metrics from database");
      // ZERO fake/demo numbers - stats remain null if error, genuine zero-states if empty
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 10000);
    return () => clearInterval(interval);
  }, []);

  const connectionLabel = loading
    ? "Checking database"
    : error
      ? "Database unavailable"
      : stats
        ? "Database connected"
        : "No telemetry available";
  const connectionTone = error
    ? admin.connectionError
    : loading
      ? admin.connectionLoading
      : admin.connectionReady;

  return (
    <div className={`${admin.surface} ${panel.adminDashboard}`}>
      <header className={admin.hero}>
        <div>
          <span className={admin.kicker}>PLATFORM OWNER / OPERATIONS</span>
          <h1 className={admin.title}>Sovereign Control Plane</h1>
          <p>
            Real-time platform overview, master provider telemetry, and margin tracking.
          </p>
        </div>
        <div className={admin.heroActions}>
          <Badge variant="outline" className={`px-3 py-1 text-xs gap-1.5 ${admin.connectionBadge} ${connectionTone}`}>
            <span className={`h-2 w-2 rounded-full ${error ? "bg-destructive" : loading ? "bg-muted-foreground" : "bg-emerald-500 animate-pulse"}`} />
            {connectionLabel}
          </Badge>
          <Button variant="outline" size="sm" onClick={fetchStats} disabled={loading} className={`${admin.refreshButton} gap-2`}>
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </header>

      {/* Error Alert if DB/API connection fails */}
      {error && (
        <div className="flex items-center justify-between p-4 rounded-lg bg-destructive/10 border border-destructive/30 text-destructive text-sm">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>Telemetry Error: {error}</span>
          </div>
          <Button variant="outline" size="sm" onClick={fetchStats} className="text-xs h-7">
            Retry
          </Button>
        </div>
      )}

      {/* Provider Verification & Catalog Alerts */}
      {((stats?.failed_verifications?.length ?? 0) > 0 || (stats?.retired_model_alerts?.length ?? 0) > 0 || (stats?.disk_usage_percent ?? 0) > 85) && (
        <div className="space-y-2">
          {stats?.failed_verifications && stats.failed_verifications.length > 0 && (
            <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-700 dark:text-amber-300 text-xs flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />
                <span><strong>Provider Verification Alerts:</strong> The following master keys need attention: {stats.failed_verifications.join(", ")}</span>
              </div>
              <Link href="/superadmin/models" className="underline font-semibold shrink-0 ml-2">Resolve in Master Keys</Link>
            </div>
          )}
          {stats?.retired_model_alerts && stats.retired_model_alerts.length > 0 && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-700 dark:text-red-300 text-xs flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-red-500" />
                <span><strong>Unavailable Model Alerts:</strong> {stats.retired_model_alerts.length} models marked unavailable or retired in catalog ({stats.retired_model_alerts.slice(0, 3).join(", ")})</span>
              </div>
              <Link href="/superadmin/models" className="underline font-semibold shrink-0 ml-2">Review Catalog</Link>
            </div>
          )}
          {(stats?.disk_usage_percent ?? 0) > 85 && (
            <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/30 text-destructive text-xs flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span><strong>Storage Warning:</strong> Disk usage at {stats?.disk_usage_percent}% ({stats?.disk_free_gb} GB remaining). Clean recordings or expand VPS volume.</span>
            </div>
          )}
        </div>
      )}

      {/* Real KPI Cards */}
      <div className={panel.metricRail}>
        <Card className="border-border/60">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground uppercase">Active Live Calls</CardTitle>
            <Radio className="h-4 w-4 text-emerald-500 animate-pulse" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-extrabold">{stats?.active_calls ?? 0}</div>
            <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
              <span className="text-emerald-500 font-medium">In-flight pipelines</span> across carriers
            </p>
          </CardContent>
        </Card>

        <Card className="border-border/60">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground uppercase">Total Minutes Delivered</CardTitle>
            <Clock className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-extrabold">{stats?.total_minutes?.toLocaleString() ?? 0}</div>
            <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
              From {stats?.total_calls ?? 0} total calls ({stats?.completed_calls ?? 0} completed)
            </p>
          </CardContent>
        </Card>

        <Card className="border-border/60">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground uppercase">Configured Model Margin</CardTitle>
            <TrendingUp className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-extrabold text-primary">
              {stats?.gross_margin_percent?.toFixed(1) ?? "—"}%
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Ratio from active catalog unit prices; excludes usage and operating costs
            </p>
          </CardContent>
        </Card>

        <Card className="border-border/60">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground uppercase">Platform Revenue (INR)</CardTitle>
            <Coins className="h-4 w-4 text-amber-500" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-extrabold text-amber-500">
              {stats?.total_revenue_inr == null ? "Unavailable" : `₹${stats.total_revenue_inr.toLocaleString()}`}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Payment amount reporting is not configured
            </p>
          </CardContent>
        </Card>
      </div>

      <section className={admin.controlDirectory} aria-labelledby="owner-controls-heading">
        <header>
          <h2 id="owner-controls-heading">Platform controls</h2>
          <p>One owner-only directory for the hosted platform. Customer workspaces keep their own business admin at <code>/admin</code>.</p>
        </header>
        <div className={admin.controlGroups}>
          {CONTROL_GROUPS.map((group) => (
            <section key={group.title} aria-label={group.title}>
              <h3>{group.title}</h3>
              <p>{group.description}</p>
              <ul>
                {group.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <li key={item.href}>
                      <Link href={item.href}>
                        <Icon aria-hidden="true" />
                        <span><strong>{item.title}</strong><small>{item.detail}</small></span>
                        <ArrowUpRight aria-hidden="true" />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      </section>
    </div>
  );
}
