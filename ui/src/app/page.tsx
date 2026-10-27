"use client";

import {
  ArrowDown,
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
import { useState } from "react";

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
const examples = {
  Support: {
    question: "I need help with my order.",
    answer: "Of course. What is your order number?",
    action: "Look up order → understand request → route next step",
  },
  Appointments: {
    question: "Can I book an appointment?",
    answer: "Sure. Which day would work for you?",
    action: "Collect preferences → check connected tools → confirm details",
  },
  "Follow-ups": {
    question: "Can you tell me more about the service?",
    answer: "Happy to help. What would you like to know?",
    action: "Understand interest → answer from context → collect next step",
  },
};
const stages = [
  {
    icon: MessageSquareText,
    title: "Speech recognition",
    text: "Turn the caller’s speech into context.",
  },
  {
    icon: Workflow,
    title: "Reasoning & workflow",
    text: "Understand the request and decide the next action.",
  },
  {
    icon: AudioLines,
    title: "Voice synthesis",
    text: "Speak the response in your configured voice.",
  },
];

export default function HomePage() {
  const branding = useClientBranding();
  const [example, setExample] = useState<keyof typeof examples>("Support");
  const selected = examples[example];
  return (
    <div className="min-h-screen bg-background text-foreground">
      <PublicHeader />
      <main id="main-content">
        <section className="relative overflow-hidden border-b border-border">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute right-0 top-0 size-[600px] rounded-full bg-cta/10 blur-[120px]"
          />
          <div className="relative mx-auto grid max-w-7xl items-center gap-14 px-5 py-16 sm:px-8 sm:py-24 lg:grid-cols-[1.1fr_1fr] lg:gap-20 lg:py-28">
            <div>
              <p className="mb-6 text-xs font-semibold uppercase tracking-[0.2em] text-cta">
                Voice AI, built around your business
              </p>
              <h1 className="text-5xl font-medium leading-[1.06] tracking-[-0.05em] sm:text-6xl lg:text-7xl">
                Good conversations.
                <br />
                <span className="text-muted-foreground">Real work, done.</span>
              </h1>
              <p className="mt-7 max-w-xl text-lg leading-8 text-muted-foreground">
                {branding.tagline}
              </p>
              <div className="mt-9 flex flex-wrap gap-3">
                <Link
                  href="/auth/login"
                  className="inline-flex items-center gap-3 rounded-lg bg-cta px-6 py-3.5 text-sm font-semibold text-cta-foreground hover:bg-cta/90"
                >
                  Open your workspace <ArrowRight className="size-4" />
                </Link>
                <Link
                  href="/pricing"
                  className="rounded-lg border border-border px-6 py-3.5 text-sm font-medium hover:bg-muted"
                >
                  Explore plans
                </Link>
              </div>
              <div className="mt-9 flex flex-wrap gap-x-6 gap-y-3 text-xs text-muted-foreground">
                {[
                  "Visual workflows",
                  "Your choice of models",
                  "Web & telephony",
                ].map((item) => (
                  <span key={item} className="flex items-center gap-2">
                    <Check className="size-3.5 text-cta" />
                    {item}
                  </span>
                ))}
              </div>
            </div>
            <div className="rounded-3xl border border-border bg-card p-5 shadow-xl shadow-black/5 sm:p-7">
              <div className="mb-7 flex items-center gap-3 border-b border-border pb-5">
                <span className="flex size-10 items-center justify-center rounded-xl bg-cta/10 text-cta">
                  <AudioLines className="size-5" />
                </span>
                <div>
                  <p className="text-sm font-semibold">
                    Your agent, in conversation
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Illustrative workflow
                  </p>
                </div>
              </div>
              <div
                className="mb-6 flex flex-wrap gap-2"
                aria-label="Conversation examples"
              >
                {(Object.keys(examples) as Array<keyof typeof examples>).map(
                  (key) => (
                    <button
                      key={key}
                      type="button"
                      aria-pressed={example === key}
                      onClick={() => setExample(key)}
                      className={`rounded-full px-3 py-2 text-xs font-medium ${example === key ? "bg-foreground text-background" : "bg-muted text-muted-foreground hover:text-foreground"}`}
                    >
                      {key}
                    </button>
                  ),
                )}
              </div>
              <div aria-live="polite" className="space-y-4">
                <div className="ml-8 rounded-2xl rounded-br-sm bg-muted px-5 py-4 text-sm leading-6">
                  {selected.question}
                </div>
                <div className="mr-8 rounded-2xl rounded-bl-sm border border-border px-5 py-4 text-sm leading-6">
                  {selected.answer}
                </div>
              </div>
              <div
                aria-hidden="true"
                className="my-7 flex h-12 items-center justify-center gap-1.5"
              >
                {[
                  10, 18, 28, 16, 38, 48, 30, 19, 36, 44, 22, 12, 29, 39, 17, 9,
                ].map((height, index) => (
                  <span
                    key={index}
                    className="w-1.5 rounded-full bg-cta/60"
                    style={{ height }}
                  />
                ))}
              </div>
              <div className="rounded-xl bg-muted/60 p-4">
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                  A clear next step
                </p>
                <p className="text-xs leading-6 text-foreground/80">
                  {selected.action}
                </p>
              </div>
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
                  From first hello to next step
                </p>
                <h2 className="max-w-xl text-4xl font-medium leading-tight tracking-tight sm:text-5xl">
                  Make conversations part of your workflow.
                </h2>
              </div>
              <p className="max-w-lg leading-7 text-muted-foreground md:justify-self-end">
                Design the journey, choose your models and connect the systems
                your team already uses. Review each run and keep improving.
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
                A stack you can choose
              </p>
              <h2 className="text-4xl font-medium leading-tight tracking-tight sm:text-5xl">
                Connect the models.
                <br />
                Shape the experience.
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
              {stages.map(({ icon: Icon, title, text }, index) => (
                <div key={title}>
                  <div className="flex items-center gap-5 rounded-2xl border border-border bg-card p-6">
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
                  {index < 2 && (
                    <ArrowDown className="mx-auto my-3 size-4 text-muted-foreground" />
                  )}
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
              Build your next conversation
            </p>
            <h2 className="text-4xl font-medium leading-tight tracking-tight sm:text-5xl">
              Start with one agent.
              <br />
              Make every next step count.
            </h2>
            <p className="mx-auto mt-6 max-w-xl leading-7 text-muted-foreground">
              Explore the platform, review the available plans and configure a
              workflow for your business.
            </p>
            <Link
              href="/pricing"
              className="mt-8 inline-flex items-center gap-3 rounded-lg bg-cta px-6 py-3.5 text-sm font-semibold text-cta-foreground hover:bg-cta/90"
            >
              Find your starting point
              <ArrowRight className="size-4" />
            </Link>
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
