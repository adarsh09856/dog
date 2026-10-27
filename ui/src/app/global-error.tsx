"use client";

import * as Sentry from "@sentry/nextjs";
import Link from "next/link";
import { useEffect } from "react";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="min-h-screen bg-background text-foreground">
        <main className="flex min-h-screen items-center justify-center p-6">
          <div className="w-full max-w-md rounded-2xl border border-border bg-card p-8 text-center shadow-lg">
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-cta font-black text-cta-foreground">KW</span>
            <h1 className="mt-6 text-2xl font-semibold tracking-tight">Something went wrong</h1>
            <p className="mt-2 text-sm text-muted-foreground">We could not load this page. Try again, or return to the home page.</p>
            <div className="mt-6 flex justify-center gap-3">
              <button type="button" onClick={reset} className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground">Try again</button>
              <Link href="/" className="rounded-lg border border-border px-4 py-2 text-sm font-medium">Home</Link>
            </div>
          </div>
        </main>
      </body>
    </html>
  );
}
