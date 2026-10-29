import { ArrowRight, AudioLines, Blocks, ChartNoAxesCombined, Headphones, Phone, Workflow } from "lucide-react";
import Link from "next/link";

import { PublicFooter, PublicHeader } from "@/components/PublicSiteChrome";

const stages = [
  { number: "01", title: "Design the conversation", text: "Build an agent workflow with prompts, branches, business tools and a defined handoff or finish point.", icon: Workflow },
  { number: "02", title: "Connect your channels", text: "Configure browser voice and supported telephony providers for the inbound or outbound work you need.", icon: Phone },
  { number: "03", title: "Choose speech models", text: "Select the available recognition, language model and voice providers for your workspace and deployment.", icon: AudioLines },
  { number: "04", title: "Review and improve", text: "Use runs, transcripts and recordings to inspect conversations and refine the workflow over time.", icon: ChartNoAxesCombined },
];

const workspaceTools = [
  ["Voice agents", "Create workflows, configure tools and test conversations before publishing."],
  ["Campaigns and telephony", "Set up supported calling channels and manage campaign activity."],
  ["CRM and appointments", "Track collected leads and appointment activity in the workspace."],
  ["Forms and web widgets", "Add supported voice and inquiry entry points to your website."],
  ["Models and files", "Manage enabled providers, speech settings and knowledge sources."],
  ["Usage and recordings", "Review runs, usage and conversation artifacts available to your plan."],
];

export default function PlatformPage() {
  return (
    <div className="public-site min-h-screen bg-background text-foreground">
      <PublicHeader />
      <main id="main-content">
        <section className="public-hero border-b border-border">
          <div className="mx-auto grid max-w-7xl gap-12 px-5 py-16 sm:px-8 sm:py-24 lg:grid-cols-[1.05fr_.95fr] lg:items-end">
            <div>
              <p className="mb-5 text-xs font-semibold uppercase tracking-[.2em] text-cta-text">The Kodewaves platform</p>
              <h1 className="max-w-3xl text-4xl font-semibold leading-[1.06] tracking-[-.045em] sm:text-6xl">From first prompt to conversations in production.</h1>
              <p className="mt-6 max-w-2xl text-lg leading-8 text-muted-foreground">Design voice agents, connect the systems and channels your deployment supports, then review how each conversation went.</p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link href="/auth/login" className="inline-flex items-center gap-2 rounded-md bg-cta px-5 py-3 text-sm font-semibold text-cta-foreground">Open workspace <ArrowRight className="size-4" /></Link>
                <Link href="/pricing" className="rounded-md border border-border px-5 py-3 text-sm font-medium hover:bg-muted">View plans</Link>
              </div>
            </div>
            <div className="grid grid-cols-2 border-y border-border">
              {stages.map(({ number, title, icon: Icon }) => (
                <div key={number} className="min-h-32 border-b border-r border-border p-5 last:border-r-0 sm:p-6 [&:nth-child(2n)]:border-r-0 [&:nth-last-child(-n+2)]:border-b-0">
                  <div className="flex items-center justify-between"><span className="font-mono text-xs text-cta-text">{number}</span><Icon className="size-4 text-muted-foreground" /></div>
                  <p className="mt-8 text-sm font-semibold">{title}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
        <section className="px-5 py-20 sm:px-8 sm:py-28">
          <div className="mx-auto max-w-7xl">
            <div className="mb-12 grid gap-6 md:grid-cols-2 md:items-end">
              <div><p className="mb-4 text-xs font-semibold uppercase tracking-[.2em] text-cta-text">A practical operating loop</p><h2 className="max-w-xl text-3xl font-medium leading-tight tracking-tight sm:text-5xl">Build, connect, test, learn.</h2></div>
              <p className="max-w-xl leading-7 text-muted-foreground md:justify-self-end">The workspace keeps agent configuration and day-to-day conversation operations together. Available tools depend on plan, enabled providers and deployment configuration.</p>
            </div>
            <div className="grid border-y border-border md:grid-cols-2">
              {stages.map(({ number, title, text, icon: Icon }, index) => (
                <article key={number} className={`grid gap-5 py-7 sm:grid-cols-[52px_1fr] sm:py-9 ${index < 2 ? "md:border-b md:border-border" : ""} ${index % 2 === 1 ? "md:border-l md:pl-8" : "md:pr-8"}`}>
                  <span className="flex size-11 items-center justify-center rounded-xl bg-cta/10 text-cta-text"><Icon className="size-5" /></span>
                  <div><p className="font-mono text-xs text-muted-foreground">STEP {number}</p><h3 className="mt-2 text-xl font-semibold tracking-tight">{title}</h3><p className="mt-3 max-w-lg text-sm leading-6 text-muted-foreground">{text}</p></div>
                </article>
              ))}
            </div>
          </div>
        </section>
        <section className="border-y border-border bg-muted/35 px-5 py-20 sm:px-8 sm:py-24">
          <div className="mx-auto max-w-7xl">
            <div className="mb-10 max-w-2xl"><p className="mb-4 text-xs font-semibold uppercase tracking-[.2em] text-cta-text">One workspace, connected work</p><h2 className="text-3xl font-medium tracking-tight sm:text-4xl">The tools around every conversation.</h2></div>
            <div className="grid border-l border-t border-border sm:grid-cols-2 lg:grid-cols-3">
              {workspaceTools.map(([title, text]) => <article key={title} className="border-b border-r border-border bg-background/50 p-6 sm:p-7"><Blocks className="size-4 text-cta-text" /><h3 className="mt-5 text-base font-semibold">{title}</h3><p className="mt-2 text-sm leading-6 text-muted-foreground">{text}</p></article>)}
            </div>
            <div className="mt-8 flex items-center gap-3 text-sm text-muted-foreground"><Headphones className="size-4 shrink-0 text-cta-text" /><p>Speech languages, voices, integrations and telephony options vary by configured provider and deployment.</p></div>
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
