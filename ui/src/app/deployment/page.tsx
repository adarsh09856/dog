import {
  ArrowRight,
  Check,
  Cloud,
  Cpu,
  Database,
  Globe,
  LockKeyhole,
  Server,
} from "lucide-react";
import Link from "next/link";

import { PublicEnterpriseLeadCTA } from "@/components/lead-forms/PublicEnterpriseLeadCTA";
import { PublicFooter, PublicHeader } from "@/components/PublicSiteChrome";

import styles from "../PublicPages.module.css";

const deploymentOptions = [
  {
    label: "01 / HOSTED",
    title: "Managed workspace",
    description: "The platform operator hosts the application and its data services. Your signed-in workspace holds organization-scoped agent and business records; external providers receive the call data needed for the services you connect.",
    icon: Cloud,
    details: [
      "Workspace access and enabled plan features",
      "Connect the providers configured for your account",
      "Review usage, runs and conversation records",
    ],
  },
  {
    label: "02 / CUSTOMER ENVIRONMENT",
    title: "Client installation",
    description: "Run a licensed installation in an agreed customer environment, with compute, providers and support scoped to the deployment.",
    icon: Server,
    details: [
      "Signed license bound to installation and approved domain",
      "Owner-managed license and installation status",
      "Customer-managed workspace operations and local access",
    ],
  },
];

const considerations = [
  { title: "Speech and model capacity", text: "Choose local or connected STT, LLM and TTS providers. Latency and language coverage depend on selected models, hardware and network.", icon: Cpu },
  { title: "Data and storage", text: "Plan database, cache and recording storage around retention needs, expected concurrency and operational backups.", icon: Database },
  { title: "Domain and access", text: "Confirm the public domain, TLS, outbound connectivity and administrative access needed by your installation.", icon: Globe },
  { title: "License and operations", text: "Client installations use an issued license and installation identity. Scope domain and optional IP restrictions with the platform administrator.", icon: LockKeyhole },
];

const planningSteps = [
  ["01", "Define call volume", "Estimate concurrent calls, expected peaks and the working hours the service must cover."],
  ["02", "Choose providers", "List language, voice, carrier and integration requirements before sizing compute."],
  ["03", "Set operating boundaries", "Agree domain, access, retention, backup and support ownership."],
  ["04", "Validate with real traffic", "Test complete calls with representative callers and measure the configured environment."],
];

export default function DeploymentPage() {
  return (
    <div className="public-site public-deployment min-h-screen bg-background text-foreground">
      <PublicHeader />
      <main id="main-content">
        <section className={styles.hero}>
          <div className={`${styles.pageFrame} ${styles.heroGrid}`}>
            <div className={styles.heroCopy}>
              <p className={styles.eyebrow}>Deployment / Operating model</p>
              <h1 className={styles.headline}>Choose where your voice operations run.</h1>
              <p className={styles.lede}>
                Use a managed workspace or discuss a licensed client installation. The right fit depends on control, providers, capacity and support requirements.
              </p>
              <div className={styles.actions}>
                <PublicEnterpriseLeadCTA
                  label="Discuss a client installation"
                  className={styles.primaryAction}
                />
                <Link href="/pricing" className={styles.secondaryAction}>Review plans and costs <ArrowRight aria-hidden className="size-4" /></Link>
                <Link href="/platform" className={styles.secondaryAction}>Explore the platform</Link>
              </div>
            </div>
            <div className={`${styles.heroRail} ${styles.productRail}`} aria-label="Deployment planning overview">
              <div className={styles.railHeading}>
                <span className={styles.railSignal} aria-hidden="true" />
                <span>DEPLOYMENT SCOPE</span>
                <span className={styles.railPreview}>PLANNING</span>
              </div>
              {[
                ["A", "Where it runs", "Hosted workspace or customer-managed environment."],
                ["B", "What it connects", "Speech, LLM, carrier and business systems."],
                ["C", "Who operates it", "Workspace roles, infrastructure and support boundaries."],
              ].map(([number, title, description]) => (
                <div className={styles.heroRailItem} key={number}>
                  <span>{number}</span><div><strong>{title}</strong><p>{description}</p></div>
                </div>
              ))}
              <div className={styles.railFooter}>
                <span>APPLICATION</span><ArrowRight aria-hidden className="size-3" /><span>PROVIDERS</span><ArrowRight aria-hidden className="size-3" /><span>OPERATIONS</span>
              </div>
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.pageFrame}>
            <div className={styles.sectionHead}>
              <div>
                <p className={styles.eyebrow}>Two operating models</p>
                <h2>Compare the environment before you configure the agent.</h2>
              </div>
              <p>
                Both use the same workflow concepts. Infrastructure responsibility, license scope and provider availability differ by deployment.
              </p>
            </div>
            <div className={styles.comparison}>
              {deploymentOptions.map(({ label, title, description, icon: Icon, details }) => (
                <article key={title} className={styles.comparisonItem}>
                  <span className={styles.comparisonLabel}>{label}</span>
                  <h3><Icon aria-hidden className="mr-2 inline size-5 text-primary" />{title}</h3>
                  <p>{description}</p>
                  <ul>
                    {details.map((detail) => <li key={detail}><Check aria-hidden />{detail}</li>)}
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
                <p className={styles.eyebrow}>Plan the environment</p>
                <h2>Four things to scope before launch.</h2>
              </div>
              <p>Map infrastructure decisions to the actual models, channels and business work the agent needs to support.</p>
            </div>
            <div className={styles.capabilityGrid}>
              {considerations.map(({ title, text, icon: Icon }) => (
                <article key={title} className={styles.capability}>
                  <span className={styles.capabilityIcon}><Icon aria-hidden className="size-5" /></span>
                  <h3>{title}</h3>
                  <p>{text}</p>
                </article>
              ))}
            </div>
            <p className="mt-5 max-w-4xl text-xs leading-6 text-muted-foreground">
              No fixed performance target is implied by a deployment choice. Measure end-to-end response time with your configured carrier, speech models, network and representative call traffic.
            </p>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.pageFrame}>
            <div className={styles.sectionHead}>
              <div>
                <p className={styles.eyebrow}>A useful deployment conversation</p>
                <h2>Move from requirements to a testable setup.</h2>
              </div>
              <p>Start with the operating needs, then check the full conversation path before rollout.</p>
            </div>
            <div className={styles.quadGrid}>
              {planningSteps.map(([number, title, text]) => (
                <article key={number} className={styles.quadItem}>
                  <span>STEP / {number}</span><h3>{title}</h3><p>{text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className={`${styles.section} pb-12`}>
          <div className={`${styles.pageFrame} ${styles.closing}`}>
            <p className={styles.eyebrow}>Next step</p>
            <h2>Find the right operating model.</h2>
            <p>Review configured hosted plans or sign in to see the capabilities and provider settings available to your workspace.</p>
            <div className={styles.actions}>
              <PublicEnterpriseLeadCTA
                label="Request a deployment consultation"
                className={styles.primaryAction}
              />
              <Link href="/pricing" className={styles.secondaryAction}>View plans <ArrowRight aria-hidden className="size-4" /></Link>
              <Link href="/auth/login" className={styles.secondaryAction}>Sign in</Link>
            </div>
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
