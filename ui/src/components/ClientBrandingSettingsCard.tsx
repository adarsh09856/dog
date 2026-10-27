"use client";

import { type FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type ClientBranding, notifyBrandingChanged } from "@/context/ClientBrandingContext";
import { apiFetch } from "@/lib/kodewavesApi";

export function ClientBrandingSettingsCard() {
  const [branding, setBranding] = useState<ClientBranding | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);

  const loadBranding = () => {
    setLoading(true);
    setError("");
    apiFetch<ClientBranding>("/installation/branding")
      .then(setBranding)
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Could not load branding."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadBranding();
  }, []);

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!branding) return;
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      await apiFetch<ClientBranding>("/installation/branding", {
        method: "PUT",
        body: JSON.stringify(branding),
      });
      notifyBrandingChanged();
      setSaved(true);
      setSaving(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save branding.");
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Client Branding</CardTitle>
        <CardDescription>Change customer-facing identity without editing application code. Installation licensing stays with the platform owner.</CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? <p className="text-sm text-muted-foreground">Loading branding…</p> : null}
        {!loading && !branding && error ? <Button type="button" variant="outline" onClick={loadBranding}>Retry</Button> : null}
        {branding ? (
          <form onSubmit={save} className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2"><Label htmlFor="brand-name">Display name</Label><Input id="brand-name" required maxLength={80} value={branding.company_name} onChange={(event) => setBranding({ ...branding, company_name: event.target.value })} /></div>
            <div className="space-y-2"><Label htmlFor="brand-logo">Logo URL or site path</Label><Input id="brand-logo" placeholder="https://example.com/logo.svg" value={branding.logo_url} onChange={(event) => setBranding({ ...branding, logo_url: event.target.value })} /></div>
            <div className="space-y-2"><Label htmlFor="brand-favicon">Browser icon URL or site path</Label><Input id="brand-favicon" value={branding.favicon_url || ""} onChange={(event) => setBranding({ ...branding, favicon_url: event.target.value })} /></div>
            <div className="space-y-2"><Label htmlFor="brand-support">Support email</Label><Input id="brand-support" type="email" value={branding.support_email || ""} onChange={(event) => setBranding({ ...branding, support_email: event.target.value })} /></div>
            <div className="space-y-2 sm:col-span-2"><Label htmlFor="brand-tagline">Short tagline</Label><Input id="brand-tagline" maxLength={160} value={branding.tagline} onChange={(event) => setBranding({ ...branding, tagline: event.target.value })} /></div>
            <div className="space-y-2"><Label htmlFor="brand-color">Primary color</Label><Input id="brand-color" type="color" value={branding.primary_color} onChange={(event) => setBranding({ ...branding, primary_color: event.target.value })} /></div>
            <div className="space-y-2"><Label htmlFor="brand-font">Font</Label><select id="brand-font" value={branding.font} onChange={(event) => setBranding({ ...branding, font: event.target.value as ClientBranding["font"] })} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"><option value="geist">Geist</option><option value="system">System</option></select></div>
            <div className="flex items-center gap-3 sm:col-span-2"><Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save branding"}</Button>{saved && <p role="status" className="text-sm text-muted-foreground">Branding saved.</p>}</div>
          </form>
        ) : null}
        {error && <p role="alert" className="mt-3 text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}
