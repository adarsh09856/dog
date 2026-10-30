"use client";

import {
  Activity,
  AlertTriangle,
  ArrowRight,
  AudioLines,
  BarChart3,
  Bot,
  Brain,
  Calendar,
  CheckCircle2,
  Clock,
  Database,
  FileText,
  Globe,
  LayoutList,
  Megaphone,
  Phone,
  PhoneCall,
  Plus,
  RefreshCw,
  ShieldCheck,
  UserCheck,
  Wallet,
  Wrench,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import panel from "@/components/layout/PanelWorkspace.module.css";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useClientBranding } from "@/context/ClientBrandingContext";
import { useAuth } from "@/lib/auth";
import { overviewApi, OverviewStatsResponse } from "@/lib/kodewavesApi";

import dashboard from "./OverviewWorkspace.module.css";

export default function OverviewPage() {
  const branding = useClientBranding();
  const { user, loading: authLoading } = useAuth();
  const [stats, setStats] = useState<OverviewStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadStats = useCallback(async () => {
    if (authLoading || !user) return;
    setLoadError(null);
    try {
      setLoading(true);
      const data = await overviewApi.getStats();
      setStats(data);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Unable to load this page. Please retry.");
      console.error("Failed to load overview metrics:", err);
    } finally {
      setLoading(false);
    }
  }, [authLoading, user]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  const sections = [
    {
      category: "BUILD",
      description: "Design conversational workflows, voice engines, and carrier connections",
      items: [
        {
          title: "Voice Agents",
          href: "/workflow",
          icon: Bot,
          badge: stats?.agents.total_agents_count ? `${stats.agents.total_agents_count} Agents` : "Core",
          desc: "Build agents with prompts, workflow branches, speech settings and channel connections.",
        },
        {
          title: "Campaigns",
          href: "/campaigns",
          icon: Megaphone,
          desc: "Schedule outbound calls and review campaign progress and outcomes.",
        },
        {
          title: "Models & Engines",
          href: "/model-configurations",
          icon: Brain,
          badge: stats?.model_health.total_models ? `${stats.model_health.total_models} Models` : "BYOK + Cloud",
          desc: "Choose configured cloud or self-hosted LLM, STT and TTS providers.",
        },
        {
          title: "Telephony",
          href: "/telephony-configurations",
          icon: Phone,
          desc: "Manage SIP trunks, Twilio, Exotel, Plivo, Telnyx, and WebRTC carrier lines.",
        },
        {
          title: "Tools & Functions",
          href: "/tools",
          icon: Wrench,
          desc: "Connect webhook tools, CRM lookups, and custom API functions to your agents.",
        },
        {
          title: "Knowledge Base",
          href: "/files",
          icon: Database,
          desc: "Upload and manage documents used by agents during conversations.",
        },
        {
          title: "Recordings & Cache",
          href: "/recordings",
          icon: AudioLines,
          desc: "Access recorded conversations, audio transcripts, and cached speech assets.",
        },
      ],
    },
    {
      category: "GROWTH AND LEADS",
      description: "Convert callers into customers with automated qualification and scheduling",
      items: [
        {
          title: "CRM Leads",
          href: "/crm",
          icon: UserCheck,
          badge: "Leads",
          desc: "Track caller contact details, qualification stages, and conversation summaries.",
        },
        {
          title: "Appointments",
          href: "/appointments",
          icon: Calendar,
          desc: "Automate calendar bookings, callback schedules, and reminder calls.",
        },
        {
          title: "Voice Forms",
          href: "/forms",
          icon: LayoutList,
          desc: "Create dynamic voice questionnaires and structured data intake surveys.",
        },
        {
          title: "Web Widgets",
          href: "/widgets",
          icon: Globe,
          badge: "WebRTC",
          desc: "Embed an instant browser-based voice assistant on your public websites.",
        },
        {
          title: "Prompt Templates",
          href: "/prompt-templates",
          icon: FileText,
          desc: "Curate reusable agent personas, compliance guardrails, and greeting scripts.",
        },
      ],
    },
    {
      category: "MANAGE AND OBSERVABILITY",
      description: "Monitor call executions, review analytics, and manage minute balances",
      items: [
        {
          title: "Agent Runs",
          href: "/usage",
          icon: Activity,
          badge: stats?.calls.calls_today ? `${stats.calls.calls_today} Today` : "Live",
          desc: "Real-time call logs, execution graphs, step-by-step latency, and transcript details.",
        },
        {
          title: "Sovereign Wallet",
          href: "/billing-sovereign",
          icon: Wallet,
          badge: stats?.wallet.total_minutes ? `${stats.wallet.total_minutes}m` : "Minutes",
          desc: "Monitor organization minutes, view ledger deductions, and manage top-up packages.",
        },
        {
          title: "Reports & Analytics",
          href: "/reports",
          icon: BarChart3,
          desc: "Inspect call disposition breakdowns, duration distributions, and export CSV reports.",
        },
      ],
    },
  ];
  return (
    <div className={dashboard.dashboard}>
      {loadError && <div role="alert" className="rounded-md border border-destructive p-3 text-sm text-destructive">{loadError}</div>}
      <div className={dashboard.inner}>
        <header className={dashboard.masthead}>
          <div className={dashboard.mastheadCopy}>
            <p className={dashboard.mastheadEyebrow}>{branding.company_name} / OPERATIONS DESK</p>
            <h1>{user?.displayName ? `Welcome, ${user.displayName.split(" ")[0]}.` : `Welcome to ${branding.company_name}`}</h1>
            <p className={dashboard.mastheadDescription}>Your voice operation, at a glance. Build the next conversation or review what happened in the last one.</p>
            <span className={dashboard.trustLine}><ShieldCheck className="h-3.5 w-3.5 text-primary" />Hosted or customer-managed deployment</span>
            <div className={dashboard.mastheadActions}>
              <Button asChild><Link href="/workflow/create"><Plus className="h-4 w-4" /> Create Agent</Link></Button>
              <Button asChild variant="outline"><Link href="/usage">Review call activity <ArrowRight className="h-4 w-4" /></Link></Button>
              <Button asChild variant="ghost"><Link href="/billing-sovereign"><Wallet className="h-4 w-4 text-primary" /> Top Up</Link></Button>
            </div>
          </div>
          <div className={dashboard.workspaceCard}>
            <div className={dashboard.workspaceCardTop}><span>YOUR WORKSPACE</span><Button variant="ghost" size="icon" aria-label="Refresh overview" onClick={loadStats} disabled={loading}><RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /></Button></div>
            <strong>Build. Connect. Operate.</strong>
            <p>Agent workflows, speech providers and conversation records in one place.</p>
            <Link href="/model-configurations">Configure your voice stack <ArrowRight size={14} /></Link>
          </div>
        </header>
        {/* Real Dynamic Stat Tiles */}
        <div className={`${panel.metricRail} ${dashboard.metrics}`} aria-label="Workspace performance">
          {/* Wallet Minutes */}
          <Card className="border border-border/60 bg-card p-5 relative overflow-hidden">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Voice Minutes
              </span>
              <div className="h-8 w-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                <Wallet className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-bold tracking-tight text-foreground">
                {stats ? stats.wallet.total_minutes.toLocaleString() : "--"}
              </span>
              <span className="text-xs text-muted-foreground">mins left</span>
            </div>
            <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
              <span>{stats ? `${stats.wallet.bonus_minutes}m bonus` : ""}</span>
              <Link href="/billing-sovereign" className="text-primary hover:underline font-medium flex items-center gap-1">
                Refill <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          </Card>

          {/* Calls Today & Week */}
          <Card className="border border-border/60 bg-card p-5 relative overflow-hidden">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Calls Handled
              </span>
              <div className="h-8 w-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                <PhoneCall className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-bold tracking-tight text-foreground">
                {stats ? stats.calls.calls_today : "--"}
              </span>
              <span className="text-xs text-muted-foreground">today</span>
            </div>
            <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
              <span>{stats ? `${stats.calls.calls_this_week} this week` : ""}</span>
              <Link href="/usage" className="text-primary hover:underline font-medium flex items-center gap-1">
                Logs <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          </Card>

          {/* Call Success Rate */}
          <Card className="border border-border/60 bg-card p-5 relative overflow-hidden">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Success Rate
              </span>
              <div className="h-8 w-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                <CheckCircle2 className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-bold tracking-tight text-foreground">
                {stats && stats.recent_runs.length > 0 ? `${stats.calls.success_rate_percent}%` : "—"}
              </span>
              <span className="text-xs text-muted-foreground">
                {stats && stats.recent_runs.length > 0 ? "recent calls" : "no calls yet"}
              </span>
            </div>
            <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
              <span>{stats ? `${stats.calls.active_calls} active calls` : ""}</span>
              <Link href="/reports" className="text-primary hover:underline font-medium flex items-center gap-1">
                Analytics <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          </Card>

          {/* Active Agents */}
          <Card className="border border-border/60 bg-card p-5 relative overflow-hidden">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Voice Agents
              </span>
              <div className="h-8 w-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                <Bot className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-bold tracking-tight text-foreground">
                {stats ? stats.agents.active_agents_count : "--"}
              </span>
              <span className="text-xs text-muted-foreground">
                of {stats ? stats.agents.total_agents_count : "--"} total
              </span>
            </div>
            <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
              <span className="font-medium text-muted-foreground">Active</span>
              <Link href="/workflow" className="text-primary hover:underline font-medium flex items-center gap-1">
                View all <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          </Card>
        </div>

        {/* Model Health Banner */}
        {stats ? stats.model_health.warnings.length > 0 ? (
          <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-amber-600 dark:text-amber-400">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 mt-0.5 shrink-0" />
              <div className="flex-1 text-xs">
              <div className="font-semibold text-sm">Model configuration needs attention</div>
                <div className="mt-1 space-y-0.5">
                  {stats.model_health.warnings.map((w, idx) => (
                    <p key={idx}>• {w}</p>
                  ))}
                </div>
              </div>
              <Button asChild size="sm" variant="outline" className="border-amber-500/50 hover:bg-amber-500/10 text-xs shrink-0">
                <Link href="/model-configurations">Configure models</Link>
              </Button>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-border bg-muted/30 p-3 px-4 flex items-center justify-between text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-primary" />
              <span className="font-medium text-foreground">Model settings</span>
              <span>No model availability warnings.</span>
            </div>
            <Link href="/model-configurations" className="text-primary hover:underline font-medium flex items-center gap-1">
              Model Settings <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        ) : (
          <div className="rounded-xl border border-border bg-muted/30 p-3 px-4 flex items-center justify-between text-xs text-muted-foreground" role="status">
            <span>{loadError ? "Model availability could not be checked." : "Checking model availability…"}</span>
            <Link href="/model-configurations" className="text-primary hover:underline font-medium flex items-center gap-1">
              Model Settings <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        )}

        {/* Recent Runs Table */}
        {stats && stats.recent_runs && stats.recent_runs.length > 0 && (
          <section className={dashboard.contentBlock} aria-labelledby="recent-calls-heading">
            <div className={dashboard.blockHeading}>
              <div><h2 id="recent-calls-heading">Recent calls &amp; executions</h2><p>Review the latest agent activity and open a run for its transcript and execution details.</p></div>
              <Link href="/usage" className="text-xs text-primary hover:underline font-medium flex items-center gap-1">
                View all runs <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            <div className={`${dashboard.callRows} divide-y divide-border/60 text-xs`}>
                {stats.recent_runs.map((run) => (
                  <div key={run.id} className="p-3.5 px-5 flex items-center justify-between hover:bg-muted/30 transition-colors">
                    <div className="flex items-center gap-3">
                      <div className="h-7 w-7 rounded-md bg-primary/10 text-primary flex items-center justify-center font-mono text-[10px] font-bold">
                        #{run.id}
                      </div>
                      <div>
                        <div className="font-medium text-foreground">{run.workflow_name}</div>
                        <div className="text-muted-foreground text-[11px] flex items-center gap-2 mt-0.5">
                          <Clock className="h-3 w-3" />
                          <span>{run.duration_seconds}s</span>
                          {run.created_at && (
                            <>
                              <span>•</span>
                              <span>{new Date(run.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge
                        variant="outline"
                        className={
                          run.status === "completed" || run.status === "success"
                            ? "border-emerald-500/30 text-emerald-500 bg-emerald-500/5 text-[10px]"
                            : "border-muted-foreground/30 text-muted-foreground text-[10px]"
                        }
                      >
                        {run.status}
                      </Badge>
                      <Button asChild variant="ghost" size="sm" className="h-7 px-2 text-xs">
                        <Link href={`/workflow/${run.workflow_id || 1}/run/${run.id}`}>
                          Inspect <ArrowRight className="ml-1 h-3 w-3" />
                        </Link>
                      </Button>
                    </div>
                  </div>
                ))}
            </div>
          </section>
        )}

        <section aria-label="Workspace tools" className={`${panel.toolDirectory} ${dashboard.toolDirectory}`}>
          {sections.map((section, index) => (
            <section key={section.category} className={panel.toolGroup} aria-label={section.category}>
              <div className={panel.groupHeading}><span>0{index + 1}</span><h2>{section.category}</h2></div>
              <p className={panel.groupDescription}>{section.description}</p>
              <div className={panel.toolItemList}>
                {section.items.map((item) => {
                  const Icon = item.icon;
                  return <Link key={item.href} href={item.href} className={panel.toolLink}><Icon size={17} /><div><h3>{item.title}</h3><p>{item.desc}</p></div><ArrowRight size={15} /></Link>;
                })}
              </div>
            </section>
          ))}
        </section>
        {/* Platform administration is available only to backend superusers. */}
        {user?.is_superuser === true && <Card className={`${dashboard.adminCard} border-border/70 bg-muted/20`}>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-primary" />
                <CardTitle className="text-base font-semibold">Platform administration</CardTitle>
              </div>
              <Badge variant="outline" className="text-xs">
                Admin Console
              </Badge>
            </div>
            <CardDescription className="text-xs">
              Manage shared model credentials, client installations, platform plans and audit records.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              <Button asChild size="sm">
                <Link href="/admin">
                  Open administration <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="sm">
                <Link href="/admin/settings">
                  Platform Settings
                </Link>
              </Button>
              <Button asChild variant="outline" size="sm">
                <Link href="/billing-sovereign">
                  Wallet &amp; Minutes
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>}
      </div>
    </div>
  );
}
