// Shared dark two-column auth shell for Kodewaves sovereign platform.
// LEFT: centered card wrapping the auth form.
// RIGHT: Kodewaves sovereign brand/value panel.

import Link from "next/link";
import type { ReactNode } from "react";

import { BrandLogo } from "@/components/BrandLogo";

const HIGHLIGHTS = [
  "Web and phone agents",
  "Self-hosted deployment option",
  "Provider and model choice",
  "Bring your own keys",
];

export function AuthShell({
  children,
  enterpriseSlot,
}: {
  children: ReactNode;
  enterpriseSlot?: ReactNode;
}) {
  return (
    <div className="grid min-h-screen w-full bg-background lg:grid-cols-[55%_45%]">
      {/* Form column (LEFT) — scrolls and stays centered */}
      <main className="flex min-h-screen flex-col overflow-y-auto">
        <div className="flex min-h-full items-center justify-center p-6 sm:p-10">
          <div className="w-full max-w-md space-y-6 rounded-2xl border border-border/60 bg-card p-6 shadow-lg sm:p-8">
            {/* Mobile-only wordmark (brand panel is hidden) */}
            <div className="lg:hidden">
              <Link href="/" aria-label="Back to home"><BrandLogo className="h-7" /></Link>
            </div>
            {children}
            <Link href="/" className="block text-center text-xs text-muted-foreground hover:text-foreground">← Back to home</Link>
          </div>
        </div>
      </main>

      {/* Brand / value panel (RIGHT) — hidden on mobile */}
      <aside className="relative hidden flex-col justify-between overflow-hidden border-l border-border/60 bg-[oklch(0.18_0.025_245)] p-10 lg:flex xl:p-14">
        {/* Ambient depth: soft radial glow behind the content */}
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 top-1/3 size-[28rem] rounded-full opacity-20 blur-3xl"
          style={{ background: "radial-gradient(circle, var(--cta), transparent 70%)" }}
        />

        <div className="relative">
          <Link href="/" aria-label="Back to home"><BrandLogo inverse className="h-8" /></Link>
        </div>

        <div className="relative max-w-md space-y-5">
          <h1 className="text-3xl font-semibold leading-tight tracking-tight text-zinc-50 xl:text-4xl">
            Good conversations. Real work, done.
          </h1>
          <ul className="flex flex-wrap gap-2">
            {HIGHLIGHTS.map((point) => (
              <li
                key={point}
                className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs font-medium text-zinc-300"
              >
                {point}
              </li>
            ))}
          </ul>
        </div>

        {/* Enterprise value block */}
        <div className="relative mb-12 max-w-md space-y-3 rounded-xl border border-white/10 bg-white/[0.03] p-5 xl:mb-16">
          <h2 className="text-sm font-semibold text-zinc-100">
            Enterprise Voice AI &amp; Private Infrastructure
          </h2>
          <p className="text-sm text-zinc-400">
            Configure voice agents for web and phone calls with the models,
            providers, and deployment controls available to your organization.
          </p>
          {enterpriseSlot}
        </div>
      </aside>
    </div>
  );
}
