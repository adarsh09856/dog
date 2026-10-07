"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
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
  Sparkles,
  UserCheck,
  Wallet,
  Wrench,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth";
import { overviewApi, OverviewStatsResponse } from "@/lib/kodewavesApi";

export default function OverviewPage() {
  const { user, loading: authLoading } = useAuth();
  const [stats, setStats] = useState<OverviewStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadStats = async () => {
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
  };

  useEffect(() => {
    if (authLoading || !user) return;
    loadStats();
  }, [authLoading, user]);

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
          desc: "Build and deploy conversational voice agents with low-latency speech pipelines.",
        },
        {
          title: "Campaigns",
          href: "/campaigns",
          icon: Megaphone,
          desc: "Schedule and execute outbound calling campaigns with smart retry logic.",
        },
        {
          title: "Models & Engines",
          href: "/model-configurations",
          icon: Brain,
          badge: stats?.model_health.total_models ? `${stats.model_health.total_models} Models` : "BYOK + Cloud",
          desc: "Configure LLM, STT, and TTS engines across Cloud (Gemini, OpenAI) & Local CPU.",
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
          desc: "Upload documents and knowledge files for instant retrieval (RAG) during calls.",
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
      category: "GROWTH & LEADS",
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
      category: "MANAGE & OBSERVABILITY",
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
    <div className="container mx-auto px-4 py-8">
      {loadError && <div role="alert" className="rounded-md border border-destructive p-3 text-sm text-destructive">{loadError}</div>}
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Sovereign Platform Banner */}
        <Card className="border border-border/70 bg-gradient-to-br from-card via-card/90 to-card/50 shadow-sm">
          <CardHeader className="pb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-primary text-xs font-semibold tracking-wider uppercase">
                <Sparkles className="h-4 w-4" />
                Kodewaves Sovereign Voice AI Command Center
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-muted-foreground hover:text-foreground"
                  onClick={loadStats}
                  disabled={loading}
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
                </Button>
                <Badge variant="outline" className="border-emerald-500/30 text-emerald-500 bg-emerald-500/5">
                  ● Platform Active
                </Badge>
              </div>
            </div>
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mt-2">
              <div>
                <CardTitle className="text-3xl font-bold tracking-tight">
                  {user?.displayName ? `Welcome, ${user.displayName.split(" ")[0]}!` : "Welcome to Kodewaves"}
                </CardTitle>
                <CardDescription className="text-sm text-muted-foreground mt-1 max-w-2xl">
                  Enterprise conversational voice AI platform with sovereign telephony, direct BYOK model pools, and low-latency voice orchestration.
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Button asChild size="sm" className="gap-1.5 shadow-sm">
                  <Link href="/workflow/create">
                    <Plus className="h-4 w-4" /> Create Agent
                  </Link>
                </Button>
                <Button asChild variant="outline" size="sm" className="gap-1.5">
                  <Link href="/billing-sovereign">
                    <Wallet className="h-4 w-4 text-emerald-500" /> Top Up
                  </Link>
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="flex flex-wrap items-center gap-3 border-t border-border/40 pt-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5 font-medium text-foreground">
                <ShieldCheck className="h-4 w-4 text-emerald-500" />
                100% Self-Hosted &amp; Sovereign
              </span>
              <span>•</span>
              <span>Cloud Models (Gemini 3.5, OpenAI, Deepgram, Sarvam, Cartesia)</span>
              <span>•</span>
              <span>Local CPU Fallback (Piper ONNX &amp; Faster-Whisper)</span>
            </div>
          </CardContent>
        </Card>

        {/* Real Dynamic Stat Tiles */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Wallet Minutes */}
          <Card className="border border-border/60 bg-card p-5 relative overflow-hidden">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Voice Minutes
              </span>
              <div className="h-8 w-8 rounded-lg bg-emerald-500/10 text-emerald-500 flex items-center justify-center">
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
              <div className="h-8 w-8 rounded-lg bg-blue-500/10 text-blue-500 flex items-center justify-center">
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
              <div className="h-8 w-8 rounded-lg bg-indigo-500/10 text-indigo-500 flex items-center justify-center">
                <CheckCircle2 className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-bold tracking-tight text-foreground">
                {stats ? `${stats.calls.success_rate_percent}%` : "--%"}
              </span>
              <span className="text-xs text-muted-foreground">completed</span>
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
              <div className="h-8 w-8 rounded-lg bg-violet-500/10 text-violet-500 flex items-center justify-center">
                <Bot className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-bold tracking-tight text-foreground">
                {stats ? stats.agents.active_agents_count : "--"}
              </span>
              <span className="text-xs text-muted-foreground">
                of {stats ? stats.agents.total_agents_count : "--"} active
              </span>
            </div>
            <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
              <span className="text-emerald-500 font-medium">Ready</span>
              <Link href="/workflow" className="text-primary hover:underline font-medium flex items-center gap-1">
                View all <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          </Card>
        </div>

        {/* Model Health Banner */}
        {stats && stats.model_health.warnings && stats.model_health.warnings.length > 0 ? (
          <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-amber-600 dark:text-amber-400">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 mt-0.5 shrink-0" />
              <div className="flex-1 text-xs">
                <div className="font-semibold text-sm">Capability Notice: Missing Layer Credentials</div>
                <div className="mt-1 space-y-0.5">
                  {stats.model_health.warnings.map((w, idx) => (
                    <p key={idx}>• {w}</p>
                  ))}
                </div>
              </div>
              <Button asChild size="sm" variant="outline" className="border-amber-500/50 hover:bg-amber-500/10 text-xs shrink-0">
                <Link href="/admin/models">Configure Keys</Link>
              </Button>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3 px-4 flex items-center justify-between text-xs text-emerald-600 dark:text-emerald-400">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              <span className="font-medium">All Voice AI Layers Operational:</span>
              <span className="text-muted-foreground">LLM, STT, and TTS voice engines verified in catalog.</span>
            </div>
            <Link href="/model-configurations" className="text-primary hover:underline font-medium flex items-center gap-1">
              Model Settings <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        )}

        {/* Recent Runs Table */}
        {stats && stats.recent_runs && stats.recent_runs.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold tracking-wider text-muted-foreground uppercase">
                Recent Calls &amp; Executions
              </h2>
              <Link href="/usage" className="text-xs text-primary hover:underline font-medium flex items-center gap-1">
                View all runs <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
            <div className="rounded-xl border border-border/70 bg-card overflow-hidden">
              <div className="divide-y divide-border/60 text-xs">
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
            </div>
          </div>
        )}

        {/* Section Groups */}
        {sections.map((section) => (
          <div key={section.category} className="space-y-4">
            <div>
              <h2 className="text-sm font-semibold tracking-wider text-muted-foreground uppercase">
                {section.category}
              </h2>
              <p className="text-xs text-muted-foreground/80 mt-0.5">
                {section.description}
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {section.items.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="group relative flex flex-col justify-between rounded-xl border border-border/60 bg-card p-5 transition-all hover:border-primary/50 hover:bg-accent/10 hover:shadow-xs"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                          <Icon className="h-4 w-4" />
                        </div>
                        {item.badge && (
                          <Badge variant="secondary" className="text-[10px] font-medium px-2 py-0.5">
                            {item.badge}
                          </Badge>
                        )}
                      </div>
                      <h3 className="font-semibold text-sm group-hover:text-primary transition-colors">
                        {item.title}
                      </h3>
                      <p className="text-xs text-muted-foreground mt-1.5 line-clamp-2 leading-relaxed">
                        {item.desc}
                      </p>
                    </div>

                    <div className="mt-4 flex items-center gap-1 text-xs font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100">
                      Open {item.title} <ArrowRight className="h-3.5 w-3.5" />
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}

        {/* Sovereign Admin Control Plane Card */}
        <Card className="border border-border/70 bg-muted/20">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-emerald-500" />
                <CardTitle className="text-base font-semibold">Sovereign Administration</CardTitle>
              </div>
              <Badge variant="outline" className="text-xs">
                Admin Console
              </Badge>
            </div>
            <CardDescription className="text-xs">
              Manage platform master API keys, toggle local CPU AI permissions, inspect system audit logs, and configure email SMTP settings.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              <Button asChild size="sm">
                <Link href="/admin">
                  Open Sovereign Admin <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
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
        </Card>
      </div>
    </div>
  );
}
