"use client";

import { ExternalLink } from "lucide-react";
import Link from "next/link";

import { CallEventsSection } from "@/components/CallEventsSection";
import { MCPSection } from "@/components/MCPSection";
import { OrganizationPreferencesSection } from "@/components/OrganizationPreferencesSection";
import { TelemetrySection } from "@/components/TelemetrySection";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function SettingsPage() {
  return (
    <div className="flex justify-center py-12 px-4">
      <div className="w-full max-w-2xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Platform Settings</h1>
          <p className="text-muted-foreground">
            Manage your platform configuration and integrations.
          </p>
        </div>

        <Card className="border-primary/40 bg-primary/5">
          <CardHeader>
            <CardTitle>Sovereign Voice & Minute Wallet</CardTitle>
            <CardDescription>
              View your organization&apos;s local minute balance, upgrade subscription plans, or bring your own API keys.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col sm:flex-row gap-3">
            <Link href="/billing-sovereign">
              <Button variant="default" className="text-xs">
                Open Sovereign Wallet & Plans
              </Button>
            </Link>
            <Link href="/model-configurations">
              <Button variant="outline" className="text-xs">
                Configure AI Provider Credentials
              </Button>
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Preferences</CardTitle>
            <CardDescription>
              Set organization-wide defaults such as the test phone number and
              timezone.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <OrganizationPreferencesSection />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>MCP Server</CardTitle>
            <CardDescription>
              Let AI agents access your Kodewaves workspace and tools via
              the Model Context Protocol.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <MCPSection />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Telemetry</CardTitle>
            <CardDescription>
              Configure Langfuse tracing for your voice agent calls.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <TelemetrySection />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Call events</CardTitle>
            <CardDescription>Configure where your organization sends call diagnostics.</CardDescription>
          </CardHeader>
          <CardContent>
            <CallEventsSection />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
