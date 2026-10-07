"use client";

import { getUserEmail } from "@/lib/auth/userDisplay";

import { ArrowRight, Building, Cpu, ExternalLink, KeyRound, Phone, ShieldAlert, ShieldCheck, Sparkles, User, Wallet } from "lucide-react";
import Link from "next/link";

import { CallEventsSection } from "@/components/CallEventsSection";
import { MCPSection } from "@/components/MCPSection";
import { OrganizationPreferencesSection } from "@/components/OrganizationPreferencesSection";
import { TelemetrySection } from "@/components/TelemetrySection";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/lib/auth";

export default function SettingsPage() {
  const { user } = useAuth();
  const isSuper = (user as any)?.is_superuser || (user as any)?.role === 'admin' || (user as any)?.is_admin;

  return (
    <div className="flex justify-center py-12 px-4">
      <div className="w-full max-w-3xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Workspace & Account Settings</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage your personal profile, active workspace defaults, and integration endpoints.
          </p>
        </div>

        {/* Superadmin Quick Access Banner (Only rendered for Superadmins) */}
        {isSuper && (
          <Card className="border-amber-500/40 bg-amber-500/10 dark:bg-amber-950/20 shadow-sm">
            <CardContent className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-amber-500/20 text-amber-600 dark:text-amber-400">
                  <ShieldCheck className="h-5 w-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm">Superadmin Access Active</span>
                    <Badge variant="outline" className="border-amber-500/40 text-amber-600 dark:text-amber-400 text-[10px] uppercase font-bold">
                      Platform Admin
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    You have global privileges to manage platform master keys, user bans, retail margins, and live monitoring.
                  </p>
                </div>
              </div>
              <Link href="/admin" className="shrink-0 w-full sm:w-auto">
                <Button className="w-full sm:w-auto gap-2 text-xs bg-amber-600 hover:bg-amber-700 text-white font-medium shadow-sm">
                  Open Admin Control Plane <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </Link>
            </CardContent>
          </Card>
        )}

        {/* User Account & Organization Card */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <User className="h-4 w-4 text-primary" />
              Account & Profile
            </CardTitle>
            <CardDescription>
              Your authenticated identity and organization workspace.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-border/60 bg-muted/20 p-3">
                <span className="text-xs text-muted-foreground font-medium">Email Address</span>
                <p className="text-sm font-semibold mt-0.5 truncate">{getUserEmail(user) || "Signed In User"}</p>
              </div>
              <div className="rounded-lg border border-border/60 bg-muted/20 p-3">
                <span className="text-xs text-muted-foreground font-medium">Account Role</span>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-sm font-semibold">{isSuper ? "Superadmin" : "Workspace Member"}</span>
                  <Badge variant={isSuper ? "default" : "secondary"} className="text-[10px]">
                    {isSuper ? "Superuser" : "Standard"}
                  </Badge>
                </div>
              </div>
            </div>
            {user && (user as any).organizationId && (
              <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 p-3 text-xs">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Building className="h-3.5 w-3.5 text-primary" />
                  <span>Workspace Organization ID:</span>
                </div>
                <code className="rounded bg-muted px-2 py-0.5 font-mono text-[11px] font-semibold">{(user as any).organizationId}</code>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Sovereign Minute Wallet & Models Card */}
        <Card className="border-primary/30 bg-primary/5">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Wallet className="h-4 w-4 text-primary" />
              Sovereign Voice & Minute Balance
            </CardTitle>
            <CardDescription>
              Check your minute quota, upgrade subscription plans, or bring your own API keys.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2.5">
            <Link href="/billing-sovereign">
              <Button variant="default" size="sm" className="text-xs gap-1.5">
                <Wallet className="h-3.5 w-3.5" />
                Open Sovereign Wallet & Plans
              </Button>
            </Link>
            <Link href="/model-configurations">
              <Button variant="outline" size="sm" className="text-xs gap-1.5">
                <Cpu className="h-3.5 w-3.5" />
                Configure AI Engines & Keys
              </Button>
            </Link>
            <Link href="/telephony-configurations">
              <Button variant="outline" size="sm" className="text-xs gap-1.5">
                <Phone className="h-3.5 w-3.5" />
                SIP Trunks & Numbers
              </Button>
            </Link>
          </CardContent>
        </Card>

        {/* Organization Preferences */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Organization Preferences</CardTitle>
            <CardDescription>
              Set organization-wide defaults such as the test phone number and default timezone.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <OrganizationPreferencesSection />
          </CardContent>
        </Card>

        {/* MCP Server */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Model Context Protocol (MCP)</CardTitle>
            <CardDescription>
              Allow external agent environments (Cursor, Windsurf, Claude Desktop) to control your Kodewaves workflows securely.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <MCPSection />
          </CardContent>
        </Card>

        {/* Telemetry (Langfuse) */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Telemetry & Tracing</CardTitle>
            <CardDescription>
              Configure Langfuse tracing for real-time observability and latency breakdown across LLM, STT, and TTS.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <TelemetrySection />
          </CardContent>
        </Card>

        {/* Call Events Webhook */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Call Diagnostics & Events</CardTitle>
            <CardDescription>Configure external webhook URLs to stream call events and diagnostic metrics.</CardDescription>
          </CardHeader>
          <CardContent>
            <CallEventsSection />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
