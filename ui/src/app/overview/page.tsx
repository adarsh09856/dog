"use client";

import Link from "next/link";
import {
  Activity,
  ArrowRight,
  AudioLines,
  BarChart3,
  Bot,
  Brain,
  Calendar,
  Database,
  FileText,
  Globe,
  LayoutList,
  Megaphone,
  Phone,
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

export default function OverviewPage() {
  const { user } = useAuth();

  const sections = [
    {
      category: "BUILD",
      description: "Design conversational workflows, voice engines, and carrier connections",
      items: [
        {
          title: "Voice Agents",
          href: "/workflow",
          icon: Bot,
          badge: "Core",
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
          badge: "BYOK + Cloud",
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
          badge: "Live",
          desc: "Real-time call logs, execution graphs, step-by-step latency, and transcript details.",
        },
        {
          title: "Sovereign Wallet",
          href: "/billing-sovereign",
          icon: Wallet,
          badge: "Minutes",
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
      <div className="max-w-6xl mx-auto space-y-10">
        {/* Sovereign Platform Banner */}
        <Card className="border border-border/70 bg-gradient-to-br from-card via-card/90 to-card/50 shadow-sm">
          <CardHeader className="pb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-primary text-xs font-semibold tracking-wider uppercase">
                <Sparkles className="h-4 w-4" />
                Kodewaves Sovereign Voice AI Command Center
              </div>
              <Badge variant="outline" className="border-emerald-500/30 text-emerald-500 bg-emerald-500/5">
                ● Platform Active
              </Badge>
            </div>
            <CardTitle className="text-3xl font-bold tracking-tight mt-1">
              {user?.displayName ? `Welcome, ${user.displayName.split(" ")[0]}!` : "Welcome to Kodewaves"}
            </CardTitle>
            <CardDescription className="text-base text-muted-foreground mt-2 max-w-3xl">
              Enterprise conversational voice AI platform with sovereign telephony, direct BYOK model pools, and low-latency voice orchestration.
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="flex flex-wrap items-center gap-3 border-t border-border/40 pt-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5 font-medium text-foreground">
                <ShieldCheck className="h-4 w-4 text-emerald-500" />
                100% Self-Hosted & Sovereign
              </span>
              <span>•</span>
              <span>All Cloud Models (Gemini 3.8, OpenAI, Deepgram, Sarvam, Cartesia)</span>
              <span>•</span>
              <span>Local CPU Fallback (Piper ONNX & Faster-Whisper)</span>
            </div>
          </CardContent>
        </Card>

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
