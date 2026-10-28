"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { apiFetch, type PublicCreditPackage } from "@/lib/kodewavesApi";
import { startConfiguredCheckout } from "@/lib/billing/checkout";
import { cn } from "@/lib/utils";

export function BuyCreditsControl({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);
  const [packages, setPackages] = useState<PublicCreditPackage[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true); setError(null);
    apiFetch<PublicCreditPackage[]>("/billing-sovereign/public/packages")
      .then((items) => { if (!cancelled) { setPackages(items); setSelected(""); } })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load credit packages."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open]);
  const buy = async () => {
    if (!selected || busy) return;
    setBusy(true); setError(null);
    try {
      const result = await startConfiguredCheckout({ package_id: selected });
      if (!result.redirected) window.location.assign("/billing-sovereign");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Checkout failed. Refresh your wallet before retrying.");
    } finally { setBusy(false); }
  };
  return (
    <Popover open={open} onOpenChange={(value) => { if (!busy) setOpen(value); }}>
      <PopoverTrigger asChild>
        <Button type="button" className={cn("bg-cta text-cta-foreground", className)}>Buy Credits</Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 space-y-3">
        <p className="text-sm font-medium">Choose a credit package</p>
        {loading ? <p className="text-sm text-muted-foreground">Loading packages…</p> : (
          <div className="space-y-2">
            {packages.length === 0 && !error && <p className="text-sm text-muted-foreground">No credit packages are available. Contact your administrator.</p>}
            {packages.map((item) => (
              <button key={item.id} type="button" disabled={busy}
                aria-pressed={selected === String(item.id)}
                onClick={() => { setSelected(String(item.id)); setError(null); }}
                className={cn("w-full rounded-md border p-3 text-left text-sm", selected === String(item.id) && "border-cta bg-cta/10")}>
                <span className="block font-medium">{item.name}</span>
                <span className="text-muted-foreground">{item.minutes + (item.bonus_minutes || 0)} minutes · {new Intl.NumberFormat(undefined, { style: "currency", currency: item.currency }).format(item.price_cents / 100)}</span>
              </button>
            ))}
          </div>
        )}
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <Button type="button" onClick={buy} disabled={loading || busy || !selected} className="w-full">
          {busy ? "Opening checkout…" : "Continue to payment"}
        </Button>
      </PopoverContent>
    </Popover>
  );
}
