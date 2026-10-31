import {
  ArrowRight,
  AudioLines,
  Blocks,
  BookOpenText,
  ChartNoAxesCombined,
  Headphones,
  Phone,
  Workflow,
} from "lucide-react";
import Link from "next/link";

import { PublicFooter, PublicHeader } from "@/components/PublicSiteChrome";

import styles from "../PublicPages.module.css";

const lifecycle = [
  ["01", "Design", "Build an agent workflow with prompts, questions, branches and a defined handoff or finish point."],
  ["02", "Connect", "Attach the tools, knowledge sources and channels that are enabled for your workspace."],
  ["03", "Test", "Exercise the workflow in browser chat or voice before publishing changes."],
  ["04", "Review", "Return to runs, transcripts and recordings to refine the next version."],
];

const workspaceTools = [
  { title: "Voice agents", text: "Create workflows, configure tools and test conversations before publishing.", icon: Workflow },
  { title: "Campaigns and telephony", text: "Set up supported calling channels and review campaign activity.", icon: Phone },
  { title: "CRM and appointments", text: "Track lead details and appointment activity collected through agent workflows.", icon: ChartNoAxesCombined },
  { title: "Forms and web widgets", text: "Add supported voice or inquiry entry points to your own website.", icon: Blocks },
  { title: "Models and knowledge", text: "Manage enabled speech providers, language settings and knowledge sources.", icon: AudioLines },
  { title: "Runs and recordings", text: "Review conversation history and artifacts available to your workspace.", icon: Headphones },
];

export default function PlatformPage() {
  return (
    <div className="public-site min-h-screen bg-background text-foreground">
      <PublicHeader />
      <main id="main-content">
        <section className={styles.hero}>
          <div className={`${styles.pageFrame} ${styles.heroGrid}`}>
            <div className={styles.heroCopy}>
              <p className={styles.eyebrow}>Platform / Voice operations</p>
              <h1 className={styles.headline}>From first prompt to conversations in production.</h1>
              <p className={styles.lede}>
                Design voice agents, connect the systems and channels your deployment supports, then review how each conversation went.
              </p>
              <div className={styles.actions}>
                <Link href="/auth/login" className={styles.primaryAction}>Open workspace <ArrowRight aria-hidden className="size-4" /></Link>
                <Link href="/pricing" className={styles.secondaryAction}>View plans</Link>
              </div>
            </div>
            <div className={`${styles.heroRail} ${styles.productRail}`} aria-label="Illustrative agent workflow">
              <div className={styles.railHeading}>
                <span className={styles.railSignal} aria-hidden="true" />
                <span>AGENT WORKFLOW</span>
                <span className={styles.railPreview}>PREVIEW</span>
              </div>
              {[
                ["01", "A conversation you can shape", "Prompts, branches and business tools in a visual workflow."],
                ["02", "Channels your team can configure", "Browser voice and supported telephone providers."],
                ["03", "A record of what happened", "Runs, transcripts and recordings for follow-through."],
              ].map(([number, title, description]) => (
                <div className={styles.heroRailItem} key={number}>
                  <span>{number}</span><div><strong>{title}</strong><p>{description}</p></div>
                </div>
              ))}
              <div className={styles.railFooter}>
                <span>DESIGN</span><ArrowRight aria-hidden className="size-3" /><span>CONNECT</span><ArrowRight aria-hidden className="size-3" /><span>REVIEW</span>
              </div>
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.pageFrame}>
            <div className={styles.sectionHead}>
              <div>
                <p className={styles.eyebrow}>A practical operating loop</p>
                <h2>Build, connect, test, learn.</h2>
              </div>
              <p>
                Keep agent configuration and day-to-day conversation operations together. Available tools depend on plan, enabled providers and deployment configuration.
              </p>
            </div>
            <div className={styles.quadGrid}>
              {lifecycle.map(([number, title, text]) => (
                <article className={styles.quadItem} key={number}>
                  <span>STEP / {number}</span>
                  <h3>{title}</h3>
                  <p>{text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.sectionMuted}>
          <div className={`${styles.pageFrame} ${styles.section}`}>
            <div className={styles.sectionHead}>
              <div>
                <p className={styles.eyebrow}>One workspace, connected work</p>
                <h2>The tools around every conversation.</h2>
              </div>
              <p>
                Organize the agent, the systems it can use and the records your team needs for follow-up.
              </p>
            </div>
            <div className={styles.capabilityGrid}>
              {workspaceTools.map(({ title, text, icon: Icon }) => (
                <article className={styles.capability} key={title}>
                  <span className={styles.capabilityIcon}><Icon aria-hidden className="size-5" /></span>
                  <h3>{title}</h3>
                  <p>{text}</p>
                </article>
              ))}
            </div>
            <div className="mt-6 flex items-start gap-3 border-t border-border pt-5 text-sm text-muted-foreground">
              <BookOpenText aria-hidden className="mt-0.5 size-4 shrink-0 text-primary" />
              <p>Speech languages, voices, integrations and telephony options vary by configured provider and deployment.</p>
            </div>
          </div>
        </section>

        <section className={`${styles.section} pb-12`}>
          <div className={`${styles.pageFrame} ${styles.closing}`}>
            <p className={styles.eyebrow}>A platform for the whole conversation</p>
            <h2>Build the workflow around the work your team owns.</h2>
            <p>Sign in to explore your enabled workspace, or review the configured plans and deployment choices.</p>
            <div className={styles.actions}>
              <Link href="/auth/login" className={styles.primaryAction}>Get started in your workspace <ArrowRight aria-hidden className="size-4" /></Link>
              <Link href="/deployment" className={styles.secondaryAction}>Compare deployments</Link>
            </div>
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
