import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6 text-foreground">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-8 text-center shadow-lg">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-cta font-black text-cta-foreground">KW</span>
        <p className="mt-6 text-sm font-semibold uppercase tracking-widest text-muted-foreground">404</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Page not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">The page you requested is not available.</p>
        <Link href="/" className="mt-6 inline-flex rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground">Go to home</Link>
      </div>
    </main>
  );
}
