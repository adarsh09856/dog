"use client";

import { type FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/kodewavesApi";

interface ClientUser {
  id: number;
  email: string | null;
  is_active: boolean;
  is_superuser: boolean;
}

export function ClientUsersSettingsCard() {
  const [users, setUsers] = useState<ClientUser[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const refresh = async () => {
    setUsers(await apiFetch<ClientUser[]>("/installation/users"));
  };

  useEffect(() => {
    void refresh().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Unable to load users."));
  }, []);

  const createUser = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await apiFetch("/installation/users", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setEmail("");
      setPassword("");
      setMessage("User created in this workspace.");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to create user.");
    } finally {
      setBusy(false);
    }
  };

  const setActive = async (user: ClientUser) => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await apiFetch(`/installation/users/${user.id}/status`, {
        method: "PUT",
        body: JSON.stringify({ active: !user.is_active }),
      });
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to update user.");
    } finally {
      setBusy(false);
    }
  };

  return <Card>
    <CardHeader>
      <CardTitle className="text-base">Workspace Users</CardTitle>
      <CardDescription>Create local users for this workspace and control their access. Signed installation seat limits apply.</CardDescription>
    </CardHeader>
    <CardContent className="space-y-5">
      <form onSubmit={createUser} className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2"><Label htmlFor="client-user-email">Email</Label><Input id="client-user-email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></div>
        <div className="space-y-2"><Label htmlFor="client-user-password">Initial password</Label><Input id="client-user-password" type="password" minLength={12} required autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} /></div>
        <div className="sm:col-span-2"><Button type="submit" disabled={busy}>{busy ? "Saving…" : "Create user"}</Button></div>
      </form>
      <div className="space-y-2">
        {users.map((user) => <div key={user.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3 text-sm">
          <div><p className="font-medium">{user.email || `User ${user.id}`}{user.is_superuser ? " · Administrator" : ""}</p><p className="text-muted-foreground">{user.is_active ? "Active" : "Suspended"}</p></div>
          {!user.is_superuser && <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => void setActive(user)}>{user.is_active ? "Suspend" : "Reactivate"}</Button>}
        </div>)}
      </div>
      {message && <p role="status" className="text-sm text-muted-foreground">{message}</p>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    </CardContent>
  </Card>;
}
