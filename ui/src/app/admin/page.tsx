"use client";

import {
  ArrowRight,
  AudioLines,
  CalendarDays,
  FileText,
  Megaphone,
  Settings,
  Sparkles,
  Users,
  Workflow,
  Wrench,
} from "lucide-react";
import Link from "next/link";

import { useClientBranding } from "@/context/ClientBrandingContext";
import { useClientEntitlements } from "@/context/ClientEntitlementsContext";
import type { ClientFeature } from "@/lib/clientEntitlements";

const GROUPS: Array<{ title: string; summary: string; links: Array<{ title: string; description: string; href: string; icon: typeof Users; feature?: ClientFeature }> }> = [
  {
    title: "Customers and growth",
    summary: "Manage the full customer journey, from inbound leads to booked appointments.",
    links: [
      { title: "CRM", description: "Track contacts, lead stages, notes and follow-up activity.", href: "/crm", icon: Users, feature: "crm" },
      { title: "Campaigns", description: "Schedule outbound campaigns and review their outcomes.", href: "/campaigns", icon: Megaphone, feature: "campaigns" },
      { title: "Appointments", description: "Manage booking calendars, callbacks and reminders.", href: "/appointments", icon: CalendarDays, feature: "appointments" },
      { title: "Voice forms", description: "Collect structured information through conversational forms.", href: "/forms", icon: FileText, feature: "forms" },
    ],
  },
  {
    title: "Voice operations",
    summary: "Configure the agents, models and tools that run your business conversations.",
    links: [
      { title: "Voice agents", description: "Build, test and publish your conversation workflows.", href: "/workflow", icon: Workflow, feature: "voice" },
      { title: "AI models", description: "Configure the language, speech and voice providers for this workspace.", href: "/model-configurations", icon: Sparkles, feature: "models" },
      { title: "Tools and integrations", description: "Connect business data and actions to your agents.", href: "/tools", icon: Wrench, feature: "tools" },
      { title: "Recordings", description: "Review call recordings and speech assets.", href: "/recordings", icon: AudioLines, feature: "recordings" },
    ],
  },
];

export default function WorkspaceAdminPage() {
  const branding = useClientBranding();
  const { isClientEdition, hasFeature } = useClientEntitlements();
  const availableGroups = GROUPS.map((group) => ({
    ...group,
    links: group.links.filter((link) => !link.feature || !isClientEdition || hasFeature(link.feature)),
  })).filter((group) => group.links.length > 0);

  return <div className="space-y-9">
    <header className="flex flex-col gap-6 border-b border-border/70 pb-7 md:flex-row md:items-end md:justify-between">
      <div className="max-w-2xl">
        <p className="mb-2 text-xs font-medium uppercase tracking-[.14em] text-muted-foreground">{branding.company_name}</p>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Workspace admin</h1>
        <p className="mt-3 max-w-[68ch] text-sm leading-6 text-muted-foreground">Manage business workflows, customer records, team access and workspace preferences from one place.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {(!isClientEdition || hasFeature("crm")) && <Link href="/crm" className="inline-flex min-h-10 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Open CRM<ArrowRight className="h-4 w-4" /></Link>}
        <Link href="/settings" className="inline-flex min-h-10 items-center gap-2 rounded-md border border-border bg-background px-4 text-sm font-medium transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><Settings className="h-4 w-4" />Workspace settings</Link>
      </div>
    </header>

    <div className="space-y-10">
      {availableGroups.map((group) => <section key={group.title} aria-labelledby={`admin-group-${group.title.replaceAll(" ", "-")}`}>
        <div className="mb-4 flex flex-col gap-1 border-b border-border/60 pb-3 sm:flex-row sm:items-end sm:justify-between"><div><h2 id={`admin-group-${group.title.replaceAll(" ", "-")}`} className="text-lg font-semibold tracking-tight">{group.title}</h2><p className="mt-1 text-sm text-muted-foreground">{group.summary}</p></div></div>
        <div className="divide-y divide-border/60">
          {group.links.map((link) => { const Icon = link.icon; return <Link key={link.href} href={link.href} className="group flex min-h-[76px] items-center gap-4 py-4 transition-colors hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-muted text-primary"><Icon className="h-5 w-5" /></span>
            <span className="min-w-0 flex-1"><span className="block text-sm font-semibold">{link.title}</span><span className="mt-1 block text-xs leading-5 text-muted-foreground">{link.description}</span></span>
            <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-1 group-hover:text-primary" />
          </Link>; })}
        </div>
      </section>)}
    </div>
  </div>;
}
