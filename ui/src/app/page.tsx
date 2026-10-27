"use client";

import {
  ArrowRight,
  AudioLines,
  Check,
  Globe2,
  Headphones,
  Layers3,
  MessageSquareText,
  Phone,
  Server,
  ShieldCheck,
  Workflow,
  Wrench,
} from "lucide-react";
import Link from "next/link";

import { PublicFooter, PublicHeader } from "@/components/PublicSiteChrome";
import { useClientBranding } from "@/context/ClientBrandingContext";

const capabilities = [
  {
    icon: Workflow,
    label: "Workflow builder",
    title: "Give every conversation a clear next step.",
    text: "Build agent workflows visually. Add questions, branches and actions that follow the information your caller provides.",
  },
  {
    icon: Phone,
    label: "Connected channels",
    title: "One agent. Web and phone.",
    text: "Connect supported telephony providers for inbound calls and outbound campaigns, or let visitors talk through a web widget.",
  },
  {
    icon: Wrench,
    label: "Business tools",
    title: "Turn a conversation into an action.",
    text: "Connect tools and APIs to look up information, collect details and move work into your business systems.",
  },
  {
    icon: Globe2,
    label: "Language & voice",
    title: "Speak your caller’s language.",
    text: "Configure models for Hindi, English and other supported languages. Test each agent with your selected models and voices before launch.",
  },
  {
    icon: Headphones,
    label: "Conversation review",
    title: "Keep the conversation in view.",
    text: "Review transcripts, recordings and workflow runs to understand what happened and improve the next conversation.",
  },
  {
    icon: Layers3,
    label: "Team operations",
    title: "A workspace for each team.",
    text: "Organize agents, provider connections and usage within workspaces, with access managed by your administrators.",
  },
];
const stages = [
  {
    number: "01",
    title: "Build the workflow",
    text: "Define prompts, branches and actions in the visual editor.",
  },
  {
    number: "02",
    title: "Test the conversation",
    text: "Run the agent in the browser and review what it heard and said.",
  },
  {
    number: "03",
    title: "Connect voice and models",
    text: "Choose speech, language and telephony providers for the deployment.",
  },
  {
    number: "04",
    title: "Operate and improve",
    text: "Handle web and phone calls, then review transcripts and recordings.",
  },
];

export default function HomePage() {
  const branding = useClientBranding();
  return (
    <div className="min-h-screen bg-background text-foreground">
      <PublicHeader />
      <main id="main-content">
        <section className="relative overflow-hidden border-b border-border">
          <div className="mx-auto grid max-w-7xl items-center gap-12 px-5 py-16 sm:px-8 sm:py-20 lg:grid-cols-[1fr_0.82fr] lg:gap-20 lg:py-24">
            <div>
              <p className="mb-6 text-xs font-semibold uppercase tracking-[0.2em] text-cta">
                Voice agent operations platform
              </p>
              <h1 className="max-w-3xl text-4xl font-semibold leading-[1.08] tracking-[-0.035em] sm:text-5xl lg:text-6xl">
                Build, test and operate voice agents.
              </h1>
              <p className="mt-7 max-w-xl text-lg leading-8 text-muted-foreground">
                {branding.tagline}
              </p>
              <p className="mt-3 max-w-xl leading-7 text-muted-foreground">
                Configure the conversation, validate it in a browser, and connect it to web or phone channels.
              </p>
              <div className="mt-9 flex flex-wrap gap-3">
                <Link
                  href="/auth/login"
                  className="inline-flex items-center gap-3 rounded-lg bg-cta px-6 py-3.5 text-sm font-semibold text-cta-foreground hover:bg-cta/90"
                >
                  Sign in to your workspace <ArrowRight className="size-4" />
                </Link>
                <Link
                  href="/pricing"
                  className="rounded-lg border border-border px-6 py-3.5 text-sm font-medium hover:bg-muted"
                >
                  View plans and deployment
                </Link>
              </div>
              <div className="mt-9 flex flex-wrap gap-x-6 gap-y-3 text-xs text-muted-foreground">
                {[
                  "Workflow editor",
                  "Browser testing",
                  "Web and telephony",
                ].map((item) => (
                  <span key={item} className="flex items-center gap-2">
                    <Check className="size-3.5 text-cta" />
                    {item}
                  </span>
                ))}
              </div>
            </div>
            <div className="overflow-hidden rounded-xl border border-border bg-card">
              <div className="flex items-center justify-between border-b border-border px-6 py-4">
                <div>
                  <p className="text-sm font-semibold">Agent lifecycle</p>
                  <p className="mt-1 text-xs text-muted-foreground">From configuration to call review</p>
                </div>
                <Workflow className="size-5 text-cta" aria-hidden="true" />
              </div>
              <ol className="divide-y divide-border">
                {stages.map(({ number, title, text }) => (
                  <li key={number} className="flex gap-5 px-6 py-5">
                    <span className="pt-0.5 font-mono text-xs tabular-nums text-muted-foreground">{number}</span>
                    <div>
                      <h2 className="text-sm font-semibold">{title}</h2>
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">{text}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </section>
        <section
          id="platform"
          className="scroll-mt-24 px-5 py-20 sm:px-8 sm:py-28"
        >
          <div className="mx-auto max-w-7xl">
            <div className="mb-12 grid gap-6 md:grid-cols-2 md:items-end">
              <div>
                <p className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-cta">
                Configure the full call lifecycle
                </p>
                <h2 className="max-w-xl text-4xl font-medium leading-tight tracking-tight sm:text-5xl">
                  One workspace for agents, channels and call review.
                </h2>
              </div>
              <p className="max-w-lg leading-7 text-muted-foreground md:justify-self-end">
                Create agents, configure speech and language providers, connect
                telephony, and review the resulting conversations from the same workspace.
              </p>
            </div>
            <div className="grid gap-px overflow-hidden rounded-2xl border border-border bg-border md:grid-cols-2 lg:grid-cols-3">
              {capabilities.map(({ icon: Icon, title, text, label }) => (
                <article key={label} className="bg-background p-7 sm:p-9">
                  <Icon className="mb-8 size-6 text-cta" />
                  <p className="mb-3 text-xs font-medium text-muted-foreground">
                    {label}
                  </p>
                  <h3 className="mb-4 text-xl font-medium leading-snug tracking-tight">
                    {title}
                  </h3>
                  <p className="text-sm leading-7 text-muted-foreground">
                    {text}
                  </p>
                </article>
              ))}
            </div>
          </div>
        </section>
        <section className="border-y border-border bg-muted/40 px-5 py-20 sm:px-8 sm:py-24">
          <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-2 lg:gap-24">
            <div>
              <p className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-cta">
                Speech configuration
              </p>
              <h2 className="text-4xl font-medium leading-tight tracking-tight sm:text-5xl">
                Configure speech for your deployment.
              </h2>
              <p className="mt-6 max-w-lg leading-8 text-muted-foreground">
                Use a speech-to-speech model or configure recognition, reasoning
                and voice separately. Provider availability depends on your
                deployment and plan.
              </p>
              <Link
                href="/pricing"
                className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-cta"
              >
                See deployment costs <ArrowRight className="size-4" />
              </Link>
            </div>
            <div>
              {[
                { icon: MessageSquareText, title: "Speech recognition", text: "Choose a supported STT provider and configure the languages your agents need." },
                { icon: Workflow, title: "Reasoning and actions", text: "Select an LLM and connect workflow branches, tools and business systems." },
                { icon: AudioLines, title: "Voice synthesis", text: "Choose a supported TTS provider, voice and speaking settings." },
              ].map(({ icon: Icon, title, text }, index) => (
                <div key={title}>
                  <div className="flex items-center gap-5 border-b border-border py-5 first:pt-0 last:border-b-0">
                    <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-cta/10 text-cta">
                      <Icon className="size-5" />
                    </span>
                    <div>
                      <h3 className="text-sm font-semibold">{title}</h3>
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">
                        {text}
                      </p>
                    </div>
                  </div>
                  {index < 2 && <div className="sr-only">Next configuration stage</div>}
                </div>
              ))}
            </div>
          </div>
        </section>
        <section
          id="deployment"
          className="scroll-mt-24 px-5 py-20 sm:px-8 sm:py-28"
        >
          <div className="mx-auto max-w-7xl">
            <div className="mb-12 max-w-2xl">
              <p className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-cta">
                Choose how you operate
              </p>
              <h2 className="text-4xl font-medium leading-tight tracking-tight sm:text-5xl">
                A workspace in the cloud.
                <br />
                Or an installation of your own.
              </h2>
            </div>
            <div className="grid gap-6 md:grid-cols-2">
              {[
                {
                  icon: Globe2,
                  title: "Managed platform",
                  text: "Build and operate agents in a hosted workspace. Your enabled plan determines available features, usage and provider options.",
                  points: [
                    "Agents and team workspaces",
                    "Connected cloud providers",
                    "Usage and conversation review",
                  ],
                },
                {
                  icon: Server,
                  title: "Client installation",
                  text: "Discuss a licensed installation for your environment. Server capacity, connected providers and ongoing support are part of the deployment scope.",
                  points: [
                    "Installation and domain license",
                    "Local or connected models",
                    "Capacity sized to your call volume",
                  ],
                },
              ].map(({ icon: Icon, title, text, points }) => (
                <article
                  key={title}
                  className="rounded-2xl border border-border bg-card p-7 sm:p-10"
                >
                  <Icon className="mb-6 size-7 text-cta" />
                  <h3 className="text-2xl font-medium tracking-tight">
                    {title}
                  </h3>
                  <p className="mt-4 text-sm leading-7 text-muted-foreground">
                    {text}
                  </p>
                  <ul className="my-7 space-y-3">
                    {points.map((point) => (
                      <li
                        key={point}
                        className="flex items-center gap-3 text-sm"
                      >
                        <ShieldCheck className="size-4 shrink-0 text-cta" />
                        {point}
                      </li>
                    ))}
                  </ul>
                  <Link
                    href="/pricing"
                    className="inline-flex items-center gap-2 text-sm font-semibold"
                  >
                    Review plans and costs
                    <ArrowRight className="size-4" />
                  </Link>
                </article>
              ))}
            </div>
          </div>
        </section>
        <section className="border-t border-border bg-muted/40 px-5 py-20 text-center sm:px-8 sm:py-24">
          <div className="mx-auto max-w-3xl">
            <p className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-cta">
              Kodewaves voice agent workspace
            </p>
            <h2 className="text-4xl font-medium leading-tight tracking-tight sm:text-5xl">
              Configure your first voice agent.
            </h2>
            <p className="mx-auto mt-6 max-w-xl leading-7 text-muted-foreground">
              Sign in to build and test an agent, or review plans and deployment
              options before getting started.
            </p>
            <Link
              href="/pricing"
              className="mt-8 inline-flex items-center gap-3 rounded-lg bg-cta px-6 py-3.5 text-sm font-semibold text-cta-foreground hover:bg-cta/90"
            >
              Review plans and deployment
              <ArrowRight className="size-4" />
            </Link>
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
