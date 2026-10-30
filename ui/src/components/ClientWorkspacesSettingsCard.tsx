"use client";

import { type FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/kodewavesApi";

interface Workspace {
  id: number;
  name: string;
}

export function ClientWorkspacesSettingsCard({ selectedOrganizationId }: { selectedOrganizationId?: number }) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void apiFetch<Workspace[]>("/installation/workspaces")
      .then(setWorkspaces)
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Unable to load workspaces."));
  }, []);

  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await apiFetch("/installation/workspaces", {
        method: "POST",
        body: JSON.stringify({ name: name.trim() }),
      });
      window.location.reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to create workspace.");
      setBusy(false);
    }
  };

  const select = async (workspace: Workspace) => {
    setBusy(true);
    setError("");
    try {
      await apiFetch(`/installation/workspaces/${workspace.id}/select`, { method: "PUT" });
      window.location.reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to switch workspace.");
      setBusy(false);
    }
  };

  return <Card>
    <CardHeader>
      <CardTitle className="text-base">Client Workspaces</CardTitle>
      <CardDescription>Create and select workspaces within the signed installation limit. User management below applies to the selected workspace.</CardDescription>
    </CardHeader>
    <CardContent className="space-y-4">
      <form onSubmit={create} className="flex flex-wrap items-end gap-3">
        <div className="min-w-56 flex-1 space-y-2"><Label htmlFor="new-client-workspace">New workspace name</Label><Input id="new-client-workspace" minLength={2} maxLength={80} required value={name} onChange={(event) => setName(event.target.value)} /></div>
        <Button type="submit" disabled={busy}>Create workspace</Button>
      </form>
      <div className="space-y-2">
        {workspaces.map((workspace) => <div key={workspace.id} className="flex items-center justify-between gap-3 rounded-md border p-3 text-sm">
          <span>{workspace.name}</span>
          {workspace.id === selectedOrganizationId ? <span className="text-muted-foreground">Selected</span> : <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => void select(workspace)}>Select</Button>}
        </div>)}
      </div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    </CardContent>
  </Card>;
}
