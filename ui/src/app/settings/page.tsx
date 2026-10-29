"use client";
import panel from "@/components/layout/PanelWorkspace.module.css";

import { ArrowRight, Building, Cpu, Phone, ShieldAlert, ShieldCheck, User, Wallet } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { CallEventsSection } from "@/components/CallEventsSection";
import { ClientBrandingSettingsCard } from "@/components/ClientBrandingSettingsCard";
import { ClientUsersSettingsCard } from "@/components/ClientUsersSettingsCard";
import { ClientWorkspacesSettingsCard } from "@/components/ClientWorkspacesSettingsCard";
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
import { useClientEntitlements } from "@/context/ClientEntitlementsContext";
import { useAuth } from "@/lib/auth";
import { getUserEmail } from "@/lib/auth/userDisplay";
import { apiFetch } from "@/lib/kodewavesApi";

interface InstallationLicenseStatus {
  edition: string;
  valid?: boolean;
  license_required?: boolean;
  installation_id?: string;
  customer_id?: string;
  domains?: string[];
  expires_at?: number;
  features?: string[];
  limits?: Record<string, number>;
  ip_ranges?: string[];
  owner_status?: "current" | "outage_grace";
  last_owner_check?: number;
  message?: string;
}

export default function SettingsPage() {
  const { user } = useAuth();
  const { hasFeature, isClientEdition } = useClientEntitlements();
  const canUseVoice = !isClientEdition || hasFeature("voice");
  const canUseBilling = !isClientEdition || hasFeature("billing");
  const canUseTelephony = !isClientEdition || hasFeature("telephony");
  const isClientAdmin = isClientEdition && user?.is_superuser === true;
  const isSuper = !isClientEdition && user?.is_superuser === true;
  const organizationId = user && "organizationId" in user ? user.organizationId : undefined;
  const selectedWorkspaceId = organizationId && Number.isInteger(Number(organizationId)) ? Number(organizationId) : undefined;
  const [installation, setInstallation] = useState<InstallationLicenseStatus | null>(null);

  useEffect(() => {
    if (!isClientAdmin) return;
    apiFetch<InstallationLicenseStatus>("/installation/license")
      .then(setInstallation)
      .catch((error: unknown) => setInstallation({
        edition: "client",
        valid: false,
        message: error instanceof Error ? error.message : "Unable to read installation status.",
      }));
  }, [isClientAdmin]);

  return (
    <div className="flex justify-center py-12 px-4">
      <div className="w-full max-w-3xl space-y-6">
        <div className={panel.collectionHeader}>
          <div><span className={panel.eyebrow}>WORKSPACE / PREFERENCES</span><h1>Workspace & Account Settings</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage your personal profile, active workspace defaults, and integration endpoints.
          </p></div>
        </div>

        {isClientAdmin && <InstallationLicenseCard installation={installation} />}
        {isClientAdmin && <ClientBrandingSettingsCard />}
        {isClientAdmin && <ClientWorkspacesSettingsCard selectedOrganizationId={selectedWorkspaceId} />}
        {isClientAdmin && <ClientUsersSettingsCard />}

        {/* Superadmin Quick Access Banner (Only rendered for Superadmins) */}
        {isSuper && (
          <Card className="border-primary/40 bg-primary/5 shadow-sm">
            <CardContent className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <ShieldCheck className="h-5 w-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm">Superadmin Access Active</span>
                    <Badge variant="outline" className="border-primary/40 text-primary text-[10px] uppercase font-bold">
                      Platform Admin
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    You have global privileges to manage platform master keys, user bans, retail margins, and live monitoring.
                  </p>
                </div>
              </div>
              <Link href="/admin" className="shrink-0 w-full sm:w-auto">
                <Button className="w-full sm:w-auto gap-2 text-xs font-medium shadow-sm">
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
                    <span className="text-sm font-semibold">{isSuper ? "Platform Owner" : isClientAdmin ? "Client Administrator" : "Workspace Member"}</span>
                  <Badge variant={isSuper || isClientAdmin ? "default" : "secondary"} className="text-[10px]">
                    {isSuper ? "Owner" : isClientAdmin ? "Administrator" : "Standard"}
                  </Badge>
                </div>
              </div>
            </div>
            {organizationId && (
              <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 p-3 text-xs">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Building className="h-3.5 w-3.5 text-primary" />
                  <span>Workspace Organization ID:</span>
                </div>
                <code className="rounded bg-muted px-2 py-0.5 font-mono text-[11px] font-semibold">{organizationId}</code>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Sovereign Minute Wallet & Models Card */}
        {(canUseVoice || canUseBilling || canUseTelephony) && <Card className="border-primary/30 bg-primary/5">
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
            {canUseBilling && <Link href="/billing-sovereign">
              <Button variant="default" size="sm" className="text-xs gap-1.5">
                <Wallet className="h-3.5 w-3.5" />
                Open Sovereign Wallet & Plans
              </Button>
            </Link>}
            {canUseVoice && <Link href="/model-configurations">
              <Button variant="outline" size="sm" className="text-xs gap-1.5">
                <Cpu className="h-3.5 w-3.5" />
                Configure AI Engines & Keys
              </Button>
            </Link>}
            {canUseTelephony && <Link href="/telephony-configurations">
              <Button variant="outline" size="sm" className="text-xs gap-1.5">
                <Phone className="h-3.5 w-3.5" />
                SIP Trunks & Numbers
              </Button>
            </Link>}
          </CardContent>
        </Card>}

        {/* Organization Preferences */}
        {canUseVoice && <Card>
          <CardHeader>
            <CardTitle className="text-base">Organization Preferences</CardTitle>
            <CardDescription>
              Set organization-wide defaults such as the test phone number and default timezone.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <OrganizationPreferencesSection />
          </CardContent>
        </Card>}

        {/* MCP Server */}
        {canUseVoice && <Card>
          <CardHeader>
            <CardTitle className="text-base">Model Context Protocol (MCP)</CardTitle>
            <CardDescription>
              Allow external agent environments (Cursor, Windsurf, Claude Desktop) to control your workflows securely.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <MCPSection />
          </CardContent>
        </Card>}

        {/* Telemetry (Langfuse) */}
        {canUseVoice && <Card>
          <CardHeader>
            <CardTitle className="text-base">Telemetry & Tracing</CardTitle>
            <CardDescription>
              Configure Langfuse tracing for real-time observability and latency breakdown across LLM, STT, and TTS.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <TelemetrySection />
          </CardContent>
        </Card>}

        {/* Call Events Webhook */}
        {canUseVoice && <Card>
          <CardHeader>
            <CardTitle className="text-base">Call Diagnostics & Events</CardTitle>
            <CardDescription>Configure external webhook URLs to stream call events and diagnostic metrics.</CardDescription>
          </CardHeader>
          <CardContent>
            <CallEventsSection />
          </CardContent>
        </Card>}
      </div>
    </div>
  );
}

function InstallationLicenseCard({
  installation,
}: {
  installation: InstallationLicenseStatus | null;
}) {
  const valid = installation?.valid === true;
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          {valid ? (
            <ShieldCheck className="h-4 w-4 text-emerald-600" />
          ) : (
            <ShieldAlert className="h-4 w-4 text-destructive" />
          )}
          Client Installation License
        </CardTitle>
        <CardDescription>
          License identity and permissions assigned by the platform owner. Your workspace administrator cannot change them.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {!installation ? (
          <p className="text-sm text-muted-foreground">Loading installation status…</p>
        ) : (
          <div className="space-y-3">
            {!valid && <p className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{installation.message || "This installation does not have an active license. Contact your platform administrator."}</p>}
            {installation.installation_id && <div className="grid gap-3 sm:grid-cols-2">
            <LicenseValue label="Status" value={!valid ? "Action required" : installation.owner_status === "outage_grace" ? "Owner connection unavailable · outage grace" : "Active · owner verified"} />
            <LicenseValue label="Last owner check" value={installation.last_owner_check ? new Date(installation.last_owner_check * 1000).toLocaleString() : "—"} />
            <LicenseValue label="Installation ID" value={installation.installation_id || "—"} />
            <LicenseValue label="Licensed domains" value={installation.domains?.join(", ") || "—"} />
            <LicenseValue
              label="Valid through"
              value={installation.expires_at
                ? new Date(installation.expires_at * 1000).toLocaleDateString()
                : "—"}
            />
            <LicenseValue label="Enabled features" value={installation.features?.join(", ") || "None"} />
            <LicenseValue
              label="Limits"
              value={installation.limits && Object.keys(installation.limits).length
                ? Object.entries(installation.limits).map(([key, value]) => `${key}: ${value}`).join(" · ")
                : "No limits listed"}
            />
            {Boolean(installation.ip_ranges?.length) && (
              <LicenseValue label="Approved server IP ranges" value={installation.ip_ranges!.join(", ")} />
            )}
            </div>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function LicenseValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-border/60 bg-muted/20 p-3">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <p className="mt-0.5 break-words text-sm font-semibold">{value}</p>
    </div>
  );
}
