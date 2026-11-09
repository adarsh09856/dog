"use client";

import { Check, Clipboard, Globe2, Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useAppConfig } from "@/context/AppConfigContext";
import { resolveBrowserBackendUrl } from "@/lib/apiClient";
import { DynamicForm, formsApi, PublicFormAccess } from "@/lib/kodewavesApi";

type Props = {
  form: DynamicForm;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function FormPublicAccessDialog({ form, open, onOpenChange }: Props) {
  const { config } = useAppConfig();
  const [access, setAccess] = useState<PublicFormAccess | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [origins, setOrigins] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rawToken, setRawToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return;
    let current = true;
    setLoading(true);
    setError(null);
    setRawToken(null);
    setCopied(false);
    formsApi.getPublicAccess(form.id).then((result) => {
      if (!current) return;
      setAccess(result);
      setEnabled(result.enabled);
      setOrigins(result.allowed_origins.join("\n"));
    }).catch((cause: unknown) => {
      if (current) setError(cause instanceof Error ? cause.message : "Could not load public form settings.");
    }).finally(() => {
      if (current) setLoading(false);
    });
    return () => { current = false; };
  }, [form.id, open]);

  const tokenConfigured = access?.token_configured ?? false;
  const apiBaseUrl = resolveBrowserBackendUrl(config?.backendApiEndpoint);
  const snippet = useMemo(() => {
    if (!rawToken) return "";
    const endpoint = `new URL(\"/api/v1/public/forms/${form.id}/submit\", ${JSON.stringify(apiBaseUrl)})`;
    return `const endpoint = ${endpoint};\nconst token = ${JSON.stringify(rawToken)};\n\nasync function submitForm(data) {\n  const response = await fetch(endpoint, {\n    method: "POST",\n    headers: { "Content-Type": "application/json", "X-Form-Token": token },\n    body: JSON.stringify({ data }),\n  });\n  if (!response.ok) throw new Error("Form submission failed");\n  return response.json();\n}\n\n// Example: submitForm({ name: "Asha", email: "asha@example.com" });`;
  }, [apiBaseUrl, form.id, rawToken]);

  const save = async (rotateToken = false) => {
    setSaving(true);
    setError(null);
    setRawToken(null);
    setCopied(false);
    try {
      const allowed_origins = origins.split(/\r?\n|,/).map((origin) => origin.trim()).filter(Boolean);
      if (enabled && allowed_origins.length === 0) {
        setError("Add at least one allowed website origin before publishing.");
        return;
      }
      const result = await formsApi.setPublicAccess(form.id, {
        enabled,
        allowed_origins,
        rotate_token: rotateToken,
      });
      setAccess(result);
      setEnabled(result.enabled);
      setOrigins(result.allowed_origins.join("\n"));
      setRawToken(result.submission_token ?? null);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Could not save public form settings.");
    } finally {
      setSaving(false);
    }
  };

  const copySnippet = async () => {
    try {
      await navigator.clipboard.writeText(snippet);
      setCopied(true);
    } catch {
      setError("Clipboard access failed. Select and copy the snippet manually.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => {
      if (!nextOpen) setRawToken(null);
      onOpenChange(nextOpen);
    }}>
      <DialogContent className="sm:max-w-2xl max-h-[88vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Globe2 className="h-5 w-5 text-primary" /> Publish “{form.title}”</DialogTitle>
          <DialogDescription>
            Accept submissions from your website with a form-specific bearer token. Submissions are stored with this form.
          </DialogDescription>
        </DialogHeader>

        {error && <div role="alert" className="rounded-xl border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"><p className="font-semibold">Couldn’t update publishing</p><p className="mt-1">{error}</p></div>}

        {loading ? (
          <div className="flex min-h-32 items-center justify-center gap-2 text-sm text-muted-foreground" role="status">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading publishing settings…
          </div>
        ) : (
          <div className="space-y-5 py-1">
            <div className="flex items-start justify-between gap-4 rounded-xl border border-border/70 bg-muted/20 p-4">
              <div className="space-y-1">
                <Label htmlFor="public-form-enabled" className="text-sm font-semibold">Public website submissions</Label>
                <p className="text-sm text-muted-foreground">Publish this form so your site can send visitor responses.</p>
              </div>
              <Switch
                id="public-form-enabled"
                aria-label="Enable public website submissions"
                checked={enabled}
                disabled={!form.is_active || saving}
                onCheckedChange={setEnabled}
              />
            </div>

            {!form.is_active && <p className="text-sm text-amber-700 dark:text-amber-300">Activate this form before publishing it.</p>}

            <div className="space-y-2">
              <Label htmlFor="public-form-origins">Allowed website origins</Label>
              <Textarea
                id="public-form-origins"
                value={origins}
                onChange={(event) => setOrigins(event.target.value)}
                placeholder={"https://example.com\nhttps://www.example.com"}
                disabled={saving}
                className="min-h-24 font-mono text-sm"
                aria-describedby="public-form-origin-help"
              />
              <p id="public-form-origin-help" className="text-xs leading-relaxed text-muted-foreground">
                Enter one origin per line, including https:// and an optional port. This is a browser CORS control only; every submission still requires the form token. It does not authenticate server-to-server requests.
              </p>
            </div>

            <div className="rounded-xl border border-border/70 bg-muted/20 p-4">
              <div className="flex items-start gap-2">
                <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <div>
                  <p className="text-sm font-semibold">Token security</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {tokenConfigured ? "A token is configured. The secret cannot be retrieved again; rotate it to issue a new one." : "A new token is generated when you publish for the first time."}
                    {" "}A browser snippet exposes its bearer token to every visitor. Keep the token on your server when possible.
                  </p>
                </div>
              </div>
            </div>

            {rawToken && (
              <div className="space-y-3 rounded-xl border border-emerald-500/40 bg-emerald-500/5 p-4">
                <div>
                  <p className="text-sm font-semibold">New submission token — copy it now</p>
                  <p className="mt-1 text-xs text-muted-foreground">For security, it will not be shown again after closing this dialog.</p>
                </div>
                <Textarea aria-label="One-time submission token" readOnly value={rawToken} className="min-h-16 break-all font-mono text-xs" />
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Button type="button" size="sm" variant="outline" onClick={() => void navigator.clipboard.writeText(rawToken).catch(() => setError("Clipboard access failed. Select and copy the token manually."))} className="gap-2">
                    <Clipboard className="h-4 w-4" /> Copy token
                  </Button>
                  <span className="text-xs text-emerald-700 dark:text-emerald-300">Token created successfully</span>
                </div>
                <div className="space-y-2 border-t border-border/60 pt-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium">Website integration example</p>
                    <Button type="button" size="sm" variant="ghost" onClick={() => void copySnippet()} className="gap-2">
                      {copied ? <Check className="h-4 w-4" /> : <Clipboard className="h-4 w-4" />}
                      {copied ? "Copied" : "Copy snippet"}
                    </Button>
                  </div>
                  <pre data-testid="public-form-integration-snippet" className="max-h-52 overflow-auto rounded-lg bg-muted p-3 text-xs leading-relaxed"><code>{snippet}</code></pre>
                </div>
              </div>
            )}

            {access?.enabled && tokenConfigured && !rawToken && (
              <p className="text-sm text-muted-foreground">The form is published. Rotate the token to create a fresh integration snippet.</p>
            )}
          </div>
        )}

        <DialogFooter className="flex-col-reverse sm:flex-row sm:justify-between">
          <Button
            type="button"
            variant="outline"
            disabled={saving || loading || !access?.token_configured || !enabled}
            onClick={() => {
              if (window.confirm("Rotate the public submission token? Existing integrations will stop working immediately.")) void save(true);
            }}
            className="gap-2"
          ><RefreshCw className="h-4 w-4" /> Rotate token</Button>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Close</Button>
            <Button type="button" onClick={() => void save(false)} disabled={saving || loading || !access || (enabled && !form.is_active)}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {saving ? "Saving…" : "Save publishing settings"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
