"use client";

import {
  ArrowRight,
  AudioLines,
  Check,
  Cloud,
  Database,
  Globe2,
  Headphones,
  MessageSquareText,
  Phone,
  Server,
  Workflow,
  Wrench,
} from "lucide-react";
import Link from "next/link";

import { VoiceOperationsIllustration } from "@/components/public/VoiceOperationsIllustration";
import { PublicFooter, PublicHeader } from "@/components/PublicSiteChrome";
import { useClientBranding } from "@/context/ClientBrandingContext";

import styles from "./PublicPages.module.css";

const operatingStages = [
  {
    number: "01",
    label: "DESIGN",
    title: "Build the voice agent workflow.",
    summary: "Set the agent’s instructions, greeting, conversation branches and actions before connecting it to callers.",
    points: ["Visual workflow builder", "Knowledge, tools and call actions"],
    icon: Workflow,
  },
  {
    number: "02",
    label: "CONNECT",
    title: "Connect browser and phone calls.",
    summary: "Run browser voice sessions, route inbound calls to an assigned workflow, or start outbound calls and campaigns through configured carriers.",
    points: ["Web voice and inbound routing", "Outbound calls and campaigns"],
    icon: Phone,
  },
  {
    number: "03",
    label: "OPERATE",
    title: "Review each call and run.",
    summary: "Inspect run status, call details, transcripts and available recordings, then use that history to improve the workflow.",
    points: ["Runs, transcripts and recordings", "Usage and campaign results"],
    icon: Headphones,
  },
];

const speechStages = [
  {
    number: "A",
    title: "Speech recognition",
    text: "Choose an enabled speech-to-text provider and a model’s supported languages to turn caller audio into text.",
    icon: MessageSquareText,
  },
  {
    number: "B",
    title: "Reasoning and actions",
    text: "Use a configured language model with the agent’s instructions, knowledge files, workflow branches and connected tools.",
    icon: Workflow,
  },
  {
    number: "C",
    title: "Voice synthesis",
    text: "Choose an enabled text-to-speech provider, voice and speaking settings for the agent’s replies.",
    icon: AudioLines,
  },
];

const platformAreas = [
  { title: "Workflow builder", text: "Design questions, branches and actions that follow the caller’s request.", icon: Workflow },
  { title: "Inbound and outbound calls", text: "Route inbound calls to an assigned agent workflow and place outbound calls through a configured telephony provider.", icon: Phone },
  { title: "Outbound campaigns", text: "Create, start and review campaigns that call contact lists using an agent workflow and configured carrier.", icon: AudioLines },
  { title: "CRM and appointments", text: "Manage contact and lead records, appointment bookings and appointment settings in the workspace.", icon: Database },
  { title: "Voice forms and web widgets", text: "Create structured forms and embed a configured browser voice agent on a website; available widget features depend on setup.", icon: Globe2 },
  { title: "Tools and knowledge", text: "Connect configured tools and maintain knowledge documents that agents can use during conversations.", icon: Wrench },
  { title: "Call and run review", text: "Review workflow runs, call outcomes, transcripts, available recordings and usage history.", icon: Headphones },
  { title: "Configured speech models", text: "Select enabled speech-to-text, language-model and text-to-speech providers; available models and languages vary by deployment.", icon: AudioLines },
];

export default function HomePage() {
  const branding = useClientBranding();

  return (
    <div className="public-site min-h-screen bg-background text-foreground">
      <PublicHeader />
      <main id="main-content">
        <section className={styles.hero}>
          <div className={`${styles.pageFrame} ${styles.heroGrid}`}>
            <div className={styles.heroCopy}>
              <p className={styles.eyebrow}>Voice operations / {branding.company_name}</p>
              <h1 className={styles.headline}>
                AI voice agents for calls.<br />
                <span className={styles.headlineAccent}>Workflows that get things done.</span>
              </h1>
              <p className={styles.lede}>{branding.tagline}</p>
              <p className="mt-3 max-w-xl text-sm leading-7 text-muted-foreground">
                Answer inbound calls, run outbound campaigns, qualify leads and book appointments. Configure browser and phone agents, speech and language models, routing, tools and knowledge in one workspace.
              </p>
              <div className={styles.actions}>
                <Link href="/auth/login" className={styles.primaryAction}>
                  Open your workspace <ArrowRight aria-hidden className="size-4" />
                </Link>
                <Link href="/platform" className={styles.secondaryAction}>
                  Explore the platform
                </Link>
              </div>
            </div>
            <div className={styles.heroVisual}>
              <VoiceOperationsIllustration />
              <div className={styles.visualCaption}>
                <span>Recognize speech / Respond / Take action</span>
                <span>Workflow preview / not live data</span>
              </div>
            </div>
          </div>
        </section>

        <div className={`${styles.pageFrame} ${styles.signalStrip}`} aria-label="Voice operations lifecycle">
          {[
            ["01", "Build an agent workflow"],
            ["02", "Route browser and phone calls"],
            ["03", "Configure STT, LLM and TTS"],
            ["04", "Review calls, runs and results"],
          ].map(([number, label]) => (
            <div className={styles.signalItem} key={number}>
              <span className={styles.signalNumber}>{number}</span>
              <span className={styles.signalLabel}>{label}</span>
            </div>
          ))}
        </div>

        <section id="platform" className={styles.section}>
          <div className={styles.pageFrame}>
            <div className={styles.sectionHead}>
              <div>
                <p className={styles.eyebrow}>Configure the full call lifecycle</p>
                <h2>Build an agent, connect a call, review the result.</h2>
              </div>
              <p>
                Configure the conversation and speech providers, route browser or telephone calls, and use workspace features such as campaigns, CRM, appointments, forms, widgets, tools and knowledge when available to your account.
              </p>
            </div>
            <div className={styles.stageGrid}>
              {operatingStages.map(({ number, label, title, summary, points, icon: Icon }) => (
                <article key={number} className={styles.stage}>
                  <div className={styles.stageTop}><span>{number} / {label}</span><Icon aria-hidden className="size-4" /></div>
                  <h3>{title}</h3>
                  <p>{summary}</p>
                  <ul className={styles.stageList}>
                    {points.map((point) => <li key={point}><Check aria-hidden />{point}</li>)}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.sectionMuted}>
          <div className={`${styles.pageFrame} ${styles.section}`}>
            <div className={styles.sectionHead}>
              <div>
                <p className={styles.eyebrow}>A configurable speech stack</p>
                <h2>Keep each part of the voice experience in view.</h2>
              </div>
              <p>
                Use a speech-to-speech option or configure recognition, reasoning and synthesis separately. Exact choices depend on enabled providers and deployment.
              </p>
            </div>
            <div className={styles.stageGrid}>
              {speechStages.map(({ number, title, text, icon: Icon }) => (
                <article className={styles.stage} key={number}>
                  <div className={styles.stageTop}><span>STAGE / {number}</span><Icon aria-hidden className="size-4" /></div>
                  <h3>{title}</h3>
                  <p>{text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.pageFrame}>
            <div className={styles.sectionHead}>
              <div>
                <p className={styles.eyebrow}>Tools around each conversation</p>
                <h2>Use calls to support real business workflows.</h2>
              </div>
              <p>
                Available tools depend on the workspace plan, enabled integrations and deployment configuration.
              </p>
            </div>
            <div className={styles.capabilityGrid}>
              {platformAreas.map(({ title, text, icon: Icon }) => (
                <article className={styles.capability} key={title}>
                  <span className={styles.capabilityIcon}><Icon aria-hidden className="size-5" /></span>
                  <h3>{title}</h3>
                  <p>{text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className={`${styles.section} ${styles.sectionMuted}`}>
          <div className={styles.pageFrame}>
            <div className={styles.sectionHead}>
              <div>
                <p className={styles.eyebrow}>Choose your operating model</p>
                <h2>A managed workspace or a licensed installation.</h2>
              </div>
              <p>Compare the deployment scope before connecting providers or planning capacity.</p>
            </div>
            <div className={styles.comparison}>
              <article className={styles.comparisonItem}>
                <span className={styles.comparisonLabel}>01 / HOSTED</span>
                <h3><Cloud aria-hidden className="mr-2 inline size-5 text-primary" />Managed platform</h3>
                <p>Build and operate agents in a hosted workspace. Your configured plan determines available features and usage.</p>
                <ul>
                  <li><Check aria-hidden />Workspace, agents and conversation review</li>
                  <li><Check aria-hidden />Connect providers enabled for your account</li>
                  <li><Check aria-hidden />Review plan terms and configured prices</li>
                </ul>
              </article>
              <article className={styles.comparisonItem}>
                <span className={styles.comparisonLabel}>02 / CUSTOMER ENVIRONMENT</span>
                <h3><Server aria-hidden className="mr-2 inline size-5 text-primary" />Client installation</h3>
                <p>Run a licensed installation in an agreed environment, with server capacity and connected providers scoped to the deployment.</p>
                <ul>
                  <li><Check aria-hidden />Installation identity and domain license</li>
                  <li><Check aria-hidden />Local or connected model options</li>
                  <li><Check aria-hidden />Capacity and support planned for expected use</li>
                </ul>
              </article>
            </div>
            <div className={`${styles.actions} mt-6`}>
              <Link href="/deployment" className={styles.secondaryAction}>Compare deployment options <ArrowRight aria-hidden className="size-4" /></Link>
              <Link href="/pricing" className={styles.secondaryAction}>See configured plans</Link>
            </div>
          </div>
        </section>

        <section className={`${styles.section} pb-12`}>
          <div className={`${styles.pageFrame} ${styles.closing}`}>
            <p className={styles.eyebrow}>{branding.company_name} voice agent workspace</p>
            <h2>Start with the work your callers need done.</h2>
            <p>Sign in to configure an agent and test its workflow, or compare plans and deployment choices with your team.</p>
            <div className={styles.actions}>
              <Link href="/auth/login" className={styles.primaryAction}>Open your workspace <ArrowRight aria-hidden className="size-4" /></Link>
              <Link href="/pricing" className={styles.secondaryAction}>Plans and pricing</Link>
            </div>
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
