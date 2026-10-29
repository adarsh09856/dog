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

import { VoiceOperationsIllustration } from "@/components/public/VoiceOperationsIllustration";
import { PublicFooter, PublicHeader } from "@/components/PublicSiteChrome";
import { useClientBranding } from "@/context/ClientBrandingContext";

const platformAreas = [
  {
    number: "01",
    label: "Design",
    title: "Shape the work before the call.",
    summary: "Build the conversation path and connect it to the systems your team already uses.",
    capabilities: [
      { icon: Workflow, title: "Workflow builder", text: "Add questions, branches and actions that follow what the caller says." },
      { icon: Wrench, title: "Business tools", text: "Look up information, collect details and pass work into business systems." },
    ],
  },
  {
    number: "02",
    label: "Connect",
    title: "Choose how people reach you.",
    summary: "Configure speech providers, languages and the channels enabled for your deployment.",
    capabilities: [
      { icon: Phone, title: "Web and telephone", text: "Connect supported carriers for inbound and outbound calls or add a web voice widget." },
      { icon: Globe2, title: "Language and voice", text: "Select from the languages and voices supported by your chosen speech models; availability varies by model and deployment." },
    ],
  },
  {
    number: "03",
    label: "Operate",
    title: "Review what happened.",
    summary: "Keep conversations and team operations in one workspace as you improve each agent.",
    capabilities: [
      { icon: Headphones, title: "Conversation review", text: "Review transcripts, recordings and workflow runs to understand each call." },
      { icon: Layers3, title: "Team operations", text: "Organize agents, provider connections and usage with workspace access controls." },
    ],
  },
];
export default function HomePage() {
  const branding = useClientBranding();
  return (
    <div className="public-site min-h-screen bg-background text-foreground">
      <PublicHeader />
      <main id="main-content">
        <section className="public-hero relative overflow-hidden border-b border-border">
          <div className="mx-auto grid max-w-7xl items-center gap-12 px-5 py-16 sm:px-8 sm:py-20 lg:grid-cols-[1fr_0.82fr] lg:gap-20 lg:py-24">
            <div>
              <p className="mb-6 inline-flex items-center gap-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                <span className="h-px w-8 bg-cta" aria-hidden="true" />
                Voice operations platform
              </p>
              <h1 className="max-w-3xl text-4xl font-semibold leading-[1.08] tracking-[-0.035em] sm:text-5xl lg:text-6xl">
                Every conversation.<br /><span className="public-heading-accent">A clear next step.</span>
              </h1>
              <p className="mt-7 max-w-xl text-lg leading-8 text-foreground/80">
                {branding.tagline}
              </p>
              <p className="mt-3 max-w-xl text-[15px] leading-7 text-muted-foreground">
                Design the conversation, validate it before launch, and operate it across browser and telephone channels.
              </p>
              <div className="mt-9 flex flex-wrap gap-3">
                <Link
                  href="/auth/login"
                  className="inline-flex items-center gap-3 rounded-md bg-cta px-5 py-3 text-sm font-semibold text-cta-foreground shadow-sm transition-colors hover:bg-cta/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >
                  Sign in to your workspace <ArrowRight className="size-4" />
                </Link>
                <Link
                  href="/pricing"
                  className="rounded-md border border-border bg-background/70 px-5 py-3 text-sm font-medium transition-colors hover:bg-background"
                >
                  View plans and deployment
                </Link>
              </div>
              <div className="mt-9 flex flex-wrap gap-x-6 gap-y-3 border-t border-border pt-5 text-xs text-muted-foreground">
                {[
                  "Workflow editor",
                  "Browser testing",
                  "Web and telephony",
                ].map((item) => (
                  <span key={item} className="flex items-center gap-2">
                    <Check className="size-3.5 text-cta-text" />
                    {item}
                  </span>
                ))}
              </div>
            </div>
            <VoiceOperationsIllustration />
          </div>
        </section>
        <section
          id="platform"
          className="scroll-mt-24 px-5 py-20 sm:px-8 sm:py-28"
        >
          <div className="mx-auto max-w-7xl">
            <div className="mb-12 grid gap-6 md:grid-cols-2 md:items-end">
              <div>
                <p className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-cta-text">
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
            <div className="grid border-y border-border md:grid-cols-3">
              {platformAreas.map(({ number, label, title, summary, capabilities: areaCapabilities }) => (
                <article key={number} className={`${number !== "03" ? "border-b border-border md:border-b-0" : ""} ${number !== "01" ? "md:border-l" : ""} py-7 md:px-7 md:py-8 md:first:pl-0 md:last:pr-0`}>
                  <div className="mb-8 flex items-center gap-3">
                    <span className="font-mono text-xs tabular-nums text-cta-text">{number}</span>
                    <span className="h-px w-7 bg-border" aria-hidden="true" />
                    <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</span>
                  </div>
                  <h3 className="max-w-xs text-xl font-semibold leading-snug tracking-tight">{title}</h3>
                  <p className="mt-3 min-h-[4.5rem] max-w-sm text-sm leading-6 text-muted-foreground">{summary}</p>
                  <ul className="mt-6 divide-y divide-border border-t border-border">
                    {areaCapabilities.map(({ icon: Icon, title: capabilityTitle, text }) => (
                      <li key={capabilityTitle} className="flex gap-3 py-4">
                        <Icon className="mt-0.5 size-4 shrink-0 text-cta-text" aria-hidden="true" />
                        <div>
                          <h4 className="text-sm font-semibold">{capabilityTitle}</h4>
                          <p className="mt-1 text-xs leading-5 text-muted-foreground">{text}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </section>
        <section className="border-y border-border bg-muted/40 px-5 py-20 sm:px-8 sm:py-24">
          <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-2 lg:gap-24">
            <div>
              <p className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-cta-text">
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
                className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-cta-text"
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
                    <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-cta/10 text-cta-text">
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
              <p className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-cta-text">
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
                  <Icon className="mb-6 size-7 text-cta-text" />
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
                        <ShieldCheck className="size-4 shrink-0 text-cta-text" />
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
        <section className="public-final-cta border-t border-border px-5 py-20 text-center sm:px-8 sm:py-24">
          <div className="mx-auto max-w-3xl">
            <p className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-cta-text">
              {branding.company_name} voice agent workspace
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
