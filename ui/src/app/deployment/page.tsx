import { ArrowRight, Cloud, Cpu, Database, Globe, LockKeyhole, Server } from "lucide-react";
import Link from "next/link";

import { PublicFooter, PublicHeader } from "@/components/PublicSiteChrome";

const deploymentOptions = [
  {
    label: "01 / HOSTED",
    title: "Managed workspace",
    description: "Use the hosted Kodewaves workspace to build and operate agents without maintaining the application servers yourself.",
    icon: Cloud,
    details: ["Workspace and team access", "Configured plans and usage", "Connect the providers enabled for your account"],
  },
  {
    label: "02 / CUSTOMER ENVIRONMENT",
    title: "Client installation",
    description: "Run a licensed installation in an agreed customer environment, with capacity and integrations scoped to the deployment.",
    icon: Server,
    details: ["Installation identity and domain binding", "Choose self-hosted or connected providers", "Size compute, storage and support for expected usage"],
  },
];

const considerations = [
  { title: "Speech and model capacity", text: "Choose local or connected STT, LLM and TTS providers. Latency and language coverage depend on the selected models, hardware and network.", icon: Cpu },
  { title: "Data and storage", text: "Plan database, cache and recording storage for retention needs, expected concurrency and operational backups.", icon: Database },
  { title: "Domain and access", text: "Confirm the public domain, TLS, outbound connectivity and administrative access needed by your installation.", icon: Globe },
  { title: "Licensing and controls", text: "Client installations use an issued license and installation identity. Scope domain and network restrictions with the platform administrator.", icon: LockKeyhole },
];

export default function DeploymentPage() {
  return (
    <div className="public-site min-h-screen bg-background text-foreground">
      <PublicHeader />
      <main id="main-content">
        <section className="public-hero border-b border-border">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 sm:py-24">
            <p className="mb-5 text-xs font-semibold uppercase tracking-[.2em] text-cta-text">Deployment choices</p>
            <h1 className="max-w-4xl text-4xl font-semibold leading-[1.06] tracking-[-.045em] sm:text-6xl">Choose where your voice operations run.</h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-muted-foreground">Use a managed workspace or discuss a licensed client installation. The right fit depends on your control, provider, capacity and support requirements.</p>
            <Link href="/pricing" className="mt-8 inline-flex items-center gap-2 rounded-md bg-cta px-5 py-3 text-sm font-semibold text-cta-foreground">Review plans and costs <ArrowRight className="size-4" /></Link>
          </div>
        </section>
        <section className="px-5 py-16 sm:px-8 sm:py-24">
          <div className="mx-auto max-w-7xl">
            <div className="grid gap-5 lg:grid-cols-2">
              {deploymentOptions.map(({ label, title, description, icon: Icon, details }) => (
                <article key={title} className="relative overflow-hidden border border-border bg-card p-7 sm:p-10">
                  <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-cta/80 via-cta/25 to-transparent" />
                  <div className="flex items-start justify-between gap-5"><div><p className="font-mono text-[11px] tracking-[.12em] text-cta-text">{label}</p><h2 className="mt-4 text-2xl font-semibold tracking-tight">{title}</h2></div><span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-cta/10 text-cta-text"><Icon className="size-5" /></span></div>
                  <p className="mt-4 max-w-xl text-sm leading-7 text-muted-foreground">{description}</p>
                  <ul className="mt-7 divide-y divide-border border-t border-border">{details.map((detail) => <li key={detail} className="py-3 text-sm text-foreground/85">{detail}</li>)}</ul>
                </article>
              ))}
            </div>
          </div>
        </section>
        <section className="border-y border-border bg-muted/35 px-5 py-16 sm:px-8 sm:py-24">
          <div className="mx-auto max-w-7xl">
            <div className="mb-10 max-w-2xl"><p className="mb-4 text-xs font-semibold uppercase tracking-[.2em] text-cta-text">Plan the environment</p><h2 className="text-3xl font-medium tracking-tight sm:text-4xl">Four things to scope before launch.</h2></div>
            <div className="grid border-l border-t border-border sm:grid-cols-2">
              {considerations.map(({ title, text, icon: Icon }, index) => <article key={title} className={`border-b border-r border-border bg-background/50 p-6 sm:p-8 ${index > 1 ? "" : ""}`}><Icon className="size-5 text-cta-text" /><h3 className="mt-5 text-base font-semibold">{title}</h3><p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">{text}</p></article>)}
            </div>
            <p className="mt-6 max-w-3xl text-xs leading-5 text-muted-foreground">No fixed performance target is implied by a deployment choice. Measure end-to-end response time with your configured carrier, speech models, network and representative call traffic.</p>
          </div>
        </section>
        <section className="px-5 py-16 text-center sm:px-8 sm:py-20"><div className="mx-auto max-w-2xl"><p className="text-xs font-semibold uppercase tracking-[.2em] text-cta-text">Next step</p><h2 className="mt-4 text-3xl font-medium tracking-tight sm:text-4xl">Find the right operating model.</h2><p className="mt-4 leading-7 text-muted-foreground">Review available plans or sign in to see the capabilities configured for your workspace.</p><div className="mt-7 flex flex-wrap justify-center gap-3"><Link href="/pricing" className="rounded-md bg-cta px-5 py-3 text-sm font-semibold text-cta-foreground">View plans</Link><Link href="/auth/login" className="rounded-md border border-border px-5 py-3 text-sm font-semibold hover:bg-muted">Sign in</Link></div></div></section>
      </main>
      <PublicFooter />
    </div>
  );
}
