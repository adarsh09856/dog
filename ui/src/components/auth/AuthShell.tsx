"use client";

import { AudioLines, ArrowUpRight, Check, Globe2, Phone, Workflow } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { BrandLogo } from "@/components/BrandLogo";
import { useClientBranding } from "@/context/ClientBrandingContext";
import styles from "./AuthShell.module.css";

const stages = [
  { icon: Phone, label: "Caller speaks", detail: "Web or telephone" },
  { icon: Workflow, label: "Agent responds", detail: "Your workflow and models" },
  { icon: Check, label: "Work moves forward", detail: "Actions and call review" },
];

export function AuthShell({ children, enterpriseSlot }: { children: ReactNode; enterpriseSlot?: ReactNode }) {
  const branding = useClientBranding();
  return (
    <div className={styles.shell}>
      <main id="main-content" className={styles.formSide}>
        <div className={styles.formHeader}>
          <Link href="/" aria-label="Back to home" className={styles.brand}><BrandLogo className="h-8" /></Link>
          <Link href="/" className={styles.homeLink}>Back to site <ArrowUpRight aria-hidden className="size-4" /></Link>
        </div>
        <div className={styles.formWrap}>
          <div className={styles.mobileIntro}>
            <p>{branding.tagline}</p>
            <p>Build the conversation, connect your channels, and review each call.</p>
          </div>
          <div className={styles.formIntro}><span className={styles.eyebrow}>YOUR WORKSPACE</span><span aria-hidden className={styles.rule} /></div>
          <div className={styles.formCard}>{children}</div>
          <p className={styles.formFoot}>A secure workspace for building and operating voice agents.</p>
        </div>
        <div className={styles.formBottom}>© {new Date().getFullYear()} {branding.company_name}</div>
      </main>
      <aside className={styles.storySide} aria-label="Voice operations overview">
        <div className={styles.storyTop}><span className={styles.storyIndex}>{branding.company_name} / VOICE OPERATIONS</span><Globe2 aria-hidden className="size-5" /></div>
        <div className={styles.storyContent}>
          <span className={styles.eyebrow}>FROM FIRST HELLO TO NEXT ACTION</span>
          <h2>{branding.tagline}</h2>
          <p>One place to shape the conversation, connect the channel, and see what happened after every call.</p>
          <div className={styles.signal} aria-hidden="true">
            {[11,28,17,37,22,53,33,61,42,67,30,49,19,39,14,25,11].map((height,i) => <span key={i} style={{height:`${height}%`,animationDelay:`${i*65}ms`}} />)}
            <AudioLines className="size-5" />
          </div>
          <ol className={styles.stages}>
            {stages.map(({icon:Icon,label,detail},index) => <li key={label}><span className={styles.stageNumber}>0{index+1}</span><Icon aria-hidden className="size-5" /><span><strong>{label}</strong><small>{detail}</small></span></li>)}
          </ol>
        </div>
        <div className={styles.storyBottom}><div><strong>Need a private deployment?</strong><span>Discuss an installation scoped to your infrastructure.</span></div>{enterpriseSlot}</div>
      </aside>
    </div>
  );
}
