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
    title: "Shape the work before the call.",
    summary: "Build the conversation path, define useful questions and connect the actions an agent can take.",
    points: ["Visual workflow builder", "Prompts, branches and tools"],
    icon: Workflow,
  },
  {
    number: "02",
    label: "CONNECT",
    title: "Choose how people reach you.",
    summary: "Configure the browser and telephone channels, plus the speech providers enabled for your deployment.",
    points: ["Browser and telephone", "Provider and language settings"],
    icon: Phone,
  },
  {
    number: "03",
    label: "OPERATE",
    title: "Review what happened.",
    summary: "Follow completed runs, transcripts and recordings so your team can improve the workflow with evidence.",
    points: ["Conversation history", "Usage and call review"],
    icon: Headphones,
  },
];

const speechStages = [
  {
    number: "A",
    title: "Speech recognition",
    text: "Select an enabled STT provider and the languages supported by the chosen model.",
    icon: MessageSquareText,
  },
  {
    number: "B",
    title: "Reasoning and actions",
    text: "Connect an LLM to your instructions, knowledge sources, workflow branches and tools.",
    icon: Workflow,
  },
  {
    number: "C",
    title: "Voice synthesis",
    text: "Choose an enabled TTS provider, voice and speaking settings for the agent.",
    icon: AudioLines,
  },
];

const platformAreas = [
  { title: "Workflow builder", text: "Design questions, branches and actions that follow the caller’s request.", icon: Workflow },
  { title: "Business tools", text: "Look up information, collect details and pass work into connected systems.", icon: Wrench },
  { title: "Web and telephone", text: "Configure browser voice and the telephony providers enabled for the workspace.", icon: Globe2 },
  { title: "Conversation review", text: "Inspect transcripts, recordings and workflow runs after each interaction.", icon: Headphones },
  { title: "Models and languages", text: "Choose from the STT, LLM and TTS providers available in your deployment.", icon: AudioLines },
  { title: "Workspace data", text: "Manage knowledge files and review usage with your team’s workspace controls.", icon: Database },
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
                Every conversation.<br />
                <span className={styles.headlineAccent}>A clear next step.</span>
              </h1>
              <p className={styles.lede}>{branding.tagline}</p>
              <p className="mt-3 max-w-xl text-sm leading-7 text-muted-foreground">
                Design how the agent responds, connect it to the systems your team uses, and review the work after each conversation.
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
                <span>Listen / Understand / Respond</span>
                <span>Workflow preview / not live data</span>
              </div>
            </div>
          </div>
        </section>

        <div className={`${styles.pageFrame} ${styles.signalStrip}`} aria-label="Voice operations lifecycle">
          {[
            ["01", "Design the conversation"],
            ["02", "Connect browser and phone"],
            ["03", "Choose enabled speech models"],
            ["04", "Review completed work"],
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
                <h2>One workspace for agents, channels and call review.</h2>
              </div>
              <p>
                Build the workflow once, connect the supported channels and providers, then keep the conversation history close to the tools that power the work.
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
                <h2>Move from a caller’s words to useful work.</h2>
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
