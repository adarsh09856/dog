"use client";
import chrome from "@/components/layout/WorkspaceChrome.module.css";

import { Check, Copy, KeyRound, Plus, RefreshCw, Trash2 } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";
import { copyTextToClipboard } from "@/lib/clipboard";
import { apiFetch } from "@/lib/kodewavesApi";

interface OrganizationApiKey {
  id: number;
  name: string;
  key_prefix: string;
  is_active: boolean;
  created_at: string;
  last_used_at?: string | null;
  archived_at?: string | null;
}

interface CreatedApiKey extends OrganizationApiKey {
  api_key: string;
}

export default function ApiKeysPage() {
  const { user, loading: authLoading } = useAuth();
  const [keys, setKeys] = useState<OrganizationApiKey[]>([]);
  const [name, setName] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [workingKeyId, setWorkingKeyId] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadKeys = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setKeys(await apiFetch<OrganizationApiKey[]>("/user/api-keys?include_archived=true"));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Could not load API keys.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authLoading || !user) return;
    void loadKeys();
  }, [authLoading, user, loadKeys]);

  const createKey = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) return;
    setSaving(true);
    setError(null);
    setNewKey(null);
    try {
      const created = await apiFetch<CreatedApiKey>("/user/api-keys", {
        method: "POST",
        body: JSON.stringify({ name: trimmedName }),
      });
      setNewKey(created.api_key);
      setName("");
      await loadKeys();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Could not create the API key.");
    } finally {
      setSaving(false);
    }
  };

  const setKeyActive = async (key: OrganizationApiKey, active: boolean) => {
    setWorkingKeyId(key.id);
    setError(null);
    try {
      await apiFetch<{ success: boolean }>(`/user/api-keys/${key.id}${active ? "/reactivate" : ""}`, {
        method: active ? "PUT" : "DELETE",
      });
      await loadKeys();
    } catch (changeError) {
      setError(changeError instanceof Error ? changeError.message : "Could not update the API key.");
    } finally {
      setWorkingKeyId(null);
    }
  };

  const copyNewKey = async () => {
    if (!newKey) return;
    try {
      await copyTextToClipboard(newKey);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch (copyError) {
      setError(copyError instanceof Error ? copyError.message : "Could not copy the API key.");
    }
  };

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 px-4 py-10">
      <header className={chrome.detailHeader}>
        <div className="flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-primary" />
          <h1 className={chrome.detailTitle}>API Keys</h1>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          Create and manage keys for this workspace&apos;s public-agent and MCP integrations.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Create an API key</CardTitle>
          <CardDescription>
            The full key is shown only once. Store it somewhere secure after creating it.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form className="flex flex-col gap-3 sm:flex-row" onSubmit={createKey}>
            <Input
              aria-label="API key name"
              autoComplete="off"
              maxLength={100}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Production integration"
              value={name}
            />
            <Button className="shrink-0" disabled={saving || !name.trim()} type="submit">
              <Plus className="mr-2 h-4 w-4" />
              {saving ? "Creating…" : "Create key"}
            </Button>
          </form>
          {newKey && (
            <div className="space-y-2 rounded-lg border border-primary/30 bg-primary/5 p-4">
              <p className="text-sm font-medium">Copy this key now. It will not be shown again.</p>
              <div className="flex flex-col gap-2 sm:flex-row">
                <code className="min-w-0 flex-1 break-all rounded-md bg-background px-3 py-2 text-xs">
                  {newKey}
                </code>
                <Button onClick={copyNewKey} type="button" variant="outline">
                  {copied ? <Check className="mr-2 h-4 w-4" /> : <Copy className="mr-2 h-4 w-4" />}
                  {copied ? "Copied" : "Copy key"}
                </Button>
              </div>
            </div>
          )}
          {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <div>
            <CardTitle className="text-base">Workspace keys</CardTitle>
            <CardDescription>Only the key prefix is stored for display.</CardDescription>
          </div>
          <Button aria-label="Refresh API keys" disabled={loading} onClick={() => void loadKeys()} size="icon" variant="outline">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading API keys…</p>
          ) : keys.length === 0 ? (
            <p className="text-sm text-muted-foreground">No API keys have been created for this workspace.</p>
          ) : (
            <ul className="space-y-3">
              {keys.map((key) => (
                <li className="flex flex-col justify-between gap-3 rounded-lg border p-4 sm:flex-row sm:items-center" key={key.id}>
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">{key.name}</p>
                      <Badge variant={key.is_active ? "default" : "secondary"}>
                        {key.is_active ? "Active" : "Archived"}
                      </Badge>
                    </div>
                    <code className="block text-xs text-muted-foreground">{key.key_prefix}••••••••</code>
                    <p className="text-xs text-muted-foreground">
                      Created {new Date(key.created_at).toLocaleString()}
                      {key.last_used_at && ` · Last used ${new Date(key.last_used_at).toLocaleString()}`}
                    </p>
                  </div>
                  <Button
                    disabled={workingKeyId === key.id}
                    onClick={() => void setKeyActive(key, !key.is_active)}
                    size="sm"
                    type="button"
                    variant={key.is_active ? "outline" : "secondary"}
                  >
                    {key.is_active ? <Trash2 className="mr-2 h-4 w-4" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                    {workingKeyId === key.id ? "Saving…" : key.is_active ? "Archive" : "Reactivate"}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
