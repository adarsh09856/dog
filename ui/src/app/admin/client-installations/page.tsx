"use client";

import { Ban, KeyRound, Plus, RefreshCw } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/kodewavesApi";

interface InstallationRecord {
  installation_id: string;
  customer_id: string;
  domains: string[];
  ip_ranges: string[];
  features: string[];
  limits: Record<string, number>;
  expires_at: number;
  token_fingerprint: string;
  revoked_at: string | null;
  renewed_at?: string | null;
  previous_token_valid_until?: string | null;
  last_seen_at: string | null;
  observed_ip?: string | null;
  integrity_failed_at: string | null;
}

interface IssuedLicense {
  installation_id: string;
  token: string;
  public_key: string;
  expires_at: number;
}

interface DomainChallenge {
  customer_id: string;
  domain: string;
  record_name: string;
  record_type: "TXT";
  record_value: string;
  expires_at: number;
}

interface IntegrityAlert {
  id: number;
  installation_id: string;
  reason: string;
  component: string;
  expected_sha256: string | null;
  observed_sha256: string | null;
  first_seen_at: string;
  last_seen_at: string;
  occurrence_count: number;
}

const DEFAULT_FEATURES = "voice, telephony, campaigns, crm, appointments, forms, widgets, knowledge_base, billing";

export default function ClientInstallationsPage() {
  const { user, loading: authLoading } = useAuth();
  const [records, setRecords] = useState<InstallationRecord[]>([]);
  const [alerts, setAlerts] = useState<IntegrityAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [renewingId, setRenewingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [issued, setIssued] = useState<IssuedLicense | null>(null);
  const [challenge, setChallenge] = useState<DomainChallenge | null>(null);
  const [challengeBusy, setChallengeBusy] = useState(false);
  const [domainVerified, setDomainVerified] = useState(false);
  const [installationId, setInstallationId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [domain, setDomain] = useState("");
  const [ipRanges, setIpRanges] = useState("");
  const [features, setFeatures] = useState(DEFAULT_FEATURES);
  const [maxCalls, setMaxCalls] = useState(2);
  const [maxSeats, setMaxSeats] = useState("");
  const [maxWorkspaces, setMaxWorkspaces] = useState("");
  const [maxAgents, setMaxAgents] = useState("");
  const [maxCampaigns, setMaxCampaigns] = useState("");
  const [days, setDays] = useState(30);

  const refresh = useCallback(async () => {
    try {
      setError("");
      const [nextRecords, nextAlerts] = await Promise.all([
        apiFetch<InstallationRecord[]>("/admin/client-installations"),
        apiFetch<IntegrityAlert[]>("/admin/client-installations/alerts"),
      ]);
      setRecords(nextRecords);
      setAlerts(nextAlerts);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load installations.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authLoading || !user) return;
    void refresh();
    const refreshTimer = window.setInterval(() => void refresh(), 30_000);
    return () => window.clearInterval(refreshTimer);
  }, [authLoading, user, refresh]);

  const createChallenge = async () => {
    setChallengeBusy(true);
    setError("");
    setDomainVerified(false);
    try {
      setChallenge(await apiFetch<DomainChallenge>("/admin/client-installations/domain-challenges", {
        method: "POST",
        body: JSON.stringify({ customer_id: customerId.trim(), domain: domain.trim() }),
      }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to create domain challenge.");
    } finally {
      setChallengeBusy(false);
    }
  };

  const verifyChallenge = async () => {
    if (!challenge) return;
    setChallengeBusy(true);
    setError("");
    try {
      await apiFetch("/admin/client-installations/domain-challenges/verify", {
        method: "POST",
        body: JSON.stringify({ customer_id: challenge.customer_id, domain: challenge.domain }),
      });
      setDomainVerified(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Domain TXT challenge is not visible yet.");
    } finally {
      setChallengeBusy(false);
    }
  };

  const issue = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setIssued(null);
    try {
      const result = await apiFetch<IssuedLicense>("/admin/client-installations", {
        method: "POST",
        body: JSON.stringify({
          installation_id: installationId.trim(),
          customer_id: customerId.trim(),
          domains: [domain.trim()],
          ip_ranges: ipRanges.split(",").map((value) => value.trim()).filter(Boolean),
          features: features.split(",").map((value) => value.trim()).filter(Boolean),
          limits: {
            max_concurrent_calls: maxCalls,
            ...(maxSeats !== "" ? { max_seats: Number(maxSeats) } : {}),
            ...(maxWorkspaces !== "" ? { max_workspaces: Number(maxWorkspaces) } : {}),
            ...(maxAgents !== "" ? { max_agents: Number(maxAgents) } : {}),
            ...(maxCampaigns !== "" ? { max_campaigns: Number(maxCampaigns) } : {}),
          },
          expires_at: Math.floor(Date.now() / 1000) + days * 86400,
        }),
      });
      setIssued(result);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to issue license.");
    } finally {
      setSubmitting(false);
    }
  };

  const revoke = async (id: string) => {
    if (!window.confirm(`Mark installation ${id} revoked? An online client will block new calls after its next owner check. A client already in an owner outage can continue only within its configured grace period and license validity.`)) return;
    setRevokingId(id);
    setError("");
    try {
      await apiFetch(`/admin/client-installations/${encodeURIComponent(id)}/revoke`, { method: "POST" });
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to record revocation.");
    } finally {
      setRevokingId(null);
    }
  };

  const renew = async (item: InstallationRecord) => {
    setRenewingId(item.installation_id);
    setError("");
    setIssued(null);
    try {
      const result = await apiFetch<IssuedLicense>(`/admin/client-installations/${encodeURIComponent(item.installation_id)}/renew`, {
        method: "POST",
        body: JSON.stringify({ expires_at: Math.max(Math.floor(Date.now() / 1000), item.expires_at) + 30 * 86400 }),
      });
      setIssued(result);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to renew installation.");
    } finally {
      setRenewingId(null);
    }
  };

  const acknowledgeAlert = async (id: number) => {
    setError("");
    try {
      await apiFetch(`/admin/client-installations/alerts/${id}/acknowledge`, { method: "POST" });
      await refresh();
      window.dispatchEvent(new Event("kodewaves-integrity-alerts-changed"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to acknowledge alert.");
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Client Installations</h1>
        <p className="mt-1 text-sm text-muted-foreground">Issue signed installation licenses and review owner records. SaaS plans are managed separately.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base"><Plus className="h-4 w-4" />Issue installation license</CardTitle>
          <CardDescription>Verify DNS control for the licensed domain before issuance. The signing key stays on the owner server; the license token is shown only once.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={issue} className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2"><Label htmlFor="installation-id">Installation ID</Label><Input id="installation-id" required value={installationId} onChange={(event) => setInstallationId(event.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="customer-id">Customer ID</Label><Input id="customer-id" required value={customerId} onChange={(event) => { setCustomerId(event.target.value); setChallenge(null); setDomainVerified(false); }} /></div>
            <div className="space-y-2"><Label htmlFor="domain">Licensed domain</Label><Input id="domain" required placeholder="client.example.com" value={domain} onChange={(event) => { setDomain(event.target.value); setChallenge(null); setDomainVerified(false); }} /></div>
            <div className="space-y-2 sm:col-span-2"><Button type="button" variant="outline" disabled={challengeBusy || !customerId.trim() || !domain.trim()} onClick={() => void createChallenge()}>{challengeBusy ? "Checking DNS…" : "Create DNS challenge"}</Button></div>
            {challenge && <div className="space-y-2 rounded-lg border p-3 text-sm sm:col-span-2">
              <p>Add this TXT record to the domain. The challenge expires {new Date(challenge.expires_at * 1000).toLocaleString()}.</p>
              <p className="break-all"><strong>Name:</strong> {challenge.record_name}</p>
              <p className="break-all"><strong>Value:</strong> {challenge.record_value}</p>
              <Button type="button" variant="outline" disabled={challengeBusy || domainVerified} onClick={() => void verifyChallenge()}>{domainVerified ? "Domain verified" : challengeBusy ? "Checking DNS…" : "Verify DNS record"}</Button>
            </div>}
            <div className="space-y-2"><Label htmlFor="ip-ranges">Allowed server IP/CIDR, optional</Label><Input id="ip-ranges" placeholder="203.0.113.10" value={ipRanges} onChange={(event) => setIpRanges(event.target.value)} /></div>
            <div className="space-y-2 sm:col-span-2"><Label htmlFor="features">Enabled features, comma separated</Label><Input id="features" value={features} onChange={(event) => setFeatures(event.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="max-calls">Maximum concurrent calls</Label><Input id="max-calls" type="number" min={1} required value={maxCalls} onChange={(event) => setMaxCalls(Number(event.target.value))} /></div>
            <div className="space-y-2"><Label htmlFor="max-seats">Maximum provisioned users, optional</Label><Input id="max-seats" type="number" min={1} value={maxSeats} onChange={(event) => setMaxSeats(event.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="max-workspaces">Maximum workspaces, optional</Label><Input id="max-workspaces" type="number" min={1} value={maxWorkspaces} onChange={(event) => setMaxWorkspaces(event.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="max-agents">Maximum provisioned agents, optional</Label><Input id="max-agents" type="number" min={0} value={maxAgents} onChange={(event) => setMaxAgents(event.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="max-campaigns">Maximum campaigns, optional</Label><Input id="max-campaigns" type="number" min={0} value={maxCampaigns} onChange={(event) => setMaxCampaigns(event.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="valid-days">Valid for days</Label><Input id="valid-days" type="number" min={1} required value={days} onChange={(event) => setDays(Number(event.target.value))} /></div>
            <div className="sm:col-span-2"><Button type="submit" disabled={submitting}>{submitting ? "Issuing…" : "Issue signed license"}</Button></div>
          </form>
        </CardContent>
      </Card>

      {error && <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
      {alerts.length > 0 && <Card className="border-destructive/50">
        <CardHeader><CardTitle className="flex items-center gap-2 text-base text-destructive"><Ban className="h-4 w-4" />Installation integrity alerts ({alerts.length})</CardTitle><CardDescription>These reports contain protected-file paths and hashes only. Acknowledging an alert does not re-enable the client installation.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          {alerts.map((alert) => <div key={alert.id} className="rounded-lg border border-destructive/30 p-3 text-sm">
            <p className="font-semibold">{alert.installation_id} · {alert.reason.replaceAll("_", " ")}</p>
            <p className="mt-1 break-all">Component: {alert.component}</p>
            <p className="mt-1 break-all text-xs text-muted-foreground">Expected: {alert.expected_sha256 || (alert.reason === "added_file" ? "Not in signed manifest" : "Unavailable")}</p>
            <p className="break-all text-xs text-muted-foreground">Observed: {alert.observed_sha256 || (alert.reason === "missing_file" ? "Missing" : "Unavailable")}</p>
            <p className="mt-1 text-xs text-muted-foreground">First seen {new Date(alert.first_seen_at).toLocaleString()} · Last seen {new Date(alert.last_seen_at).toLocaleString()} · {alert.occurrence_count} check{alert.occurrence_count === 1 ? "" : "s"}</p>
            <Button className="mt-2" type="button" variant="outline" size="sm" onClick={() => void acknowledgeAlert(alert.id)}>Acknowledge</Button>
          </div>)}
        </CardContent>
      </Card>}
      {issued && (
        <Card className="border-amber-500/50">
          <CardHeader><CardTitle className="flex items-center gap-2 text-base"><KeyRound className="h-4 w-4" />Issued: {issued.installation_id}</CardTitle><CardDescription>Copy these values into the client installation configuration now. The token cannot be retrieved from this screen later.</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            <div><Label htmlFor="issued-token">Signed license token</Label><textarea id="issued-token" readOnly value={issued.token} className="mt-1 h-24 w-full rounded-md border bg-background p-2 font-mono text-xs" /></div>
            <div><Label htmlFor="issued-public-key">Public verification key</Label><Input id="issued-public-key" readOnly value={issued.public_key} className="font-mono text-xs" /></div>
            <Button variant="outline" onClick={() => setIssued(null)}>I have saved the token</Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between"><div><CardTitle className="text-base">Issued installations</CardTitle><CardDescription>Metadata only; signed tokens are not stored here. Online clients check owner status periodically; offline clients use the configured grace period.</CardDescription></div><Button variant="outline" size="sm" onClick={() => void refresh()}><RefreshCw className="mr-2 h-4 w-4" />Refresh</Button></CardHeader>
        <CardContent className="space-y-3">
          {loading && <p className="text-sm text-muted-foreground">Loading installations…</p>}
          {!loading && records.length === 0 && <p className="text-sm text-muted-foreground">No installations issued yet.</p>}
          {records.map((item) => (
            <div key={item.installation_id} className="rounded-lg border p-4 text-sm">
              <div className="flex flex-wrap justify-between gap-2"><strong>{item.installation_id}</strong><span>{item.customer_id}</span></div>
              <p className="mt-1 text-muted-foreground">{item.domains.join(", ")} · Expires {new Date(item.expires_at * 1000).toLocaleDateString()}</p>
              {item.ip_ranges.length > 0 && <p className="mt-1 text-muted-foreground">Allowed source IPs: {item.ip_ranges.join(", ")}</p>}
              <p className="mt-1 text-muted-foreground">{item.features.join(", ") || "No features"} · {item.limits.max_concurrent_calls ?? 0} concurrent calls</p>
              <p className="mt-1 text-muted-foreground">Provisioned caps: {item.limits.max_seats ?? "unlimited"} users · {item.limits.max_workspaces ?? "unlimited"} workspaces · {item.limits.max_agents ?? "unlimited"} agents · {item.limits.max_campaigns ?? "unlimited"} campaigns</p>
              <p className="mt-1 text-muted-foreground">{item.last_seen_at ? `Last owner check ${new Date(item.last_seen_at).toLocaleString()}` : "No client check received"}</p>
              {item.observed_ip && <p className="mt-1 text-muted-foreground">Last observed source IP {item.observed_ip}</p>}
              {item.renewed_at && <p className="mt-1 text-muted-foreground">Renewed {new Date(item.renewed_at).toLocaleString()}</p>}
              {item.previous_token_valid_until && new Date(item.previous_token_valid_until).getTime() > Date.now() && <p className="mt-1 text-muted-foreground">Previous token handover ends {new Date(item.previous_token_valid_until).toLocaleString()}</p>}
              {item.integrity_failed_at && <div className="mt-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-destructive"><p className="font-semibold">Integrity alert received {new Date(item.integrity_failed_at).toLocaleString()}.</p><p className="mt-1">This installation is blocked and cannot be renewed. Preserve the incident, restore a clean approved release, and issue a replacement with a new installation ID. Acknowledgment records review only.</p></div>}
              {item.revoked_at ? <p className="mt-2 text-destructive">Marked revoked {new Date(item.revoked_at).toLocaleString()}. The client applies this after its next successful owner check.</p> : <div className="mt-3 flex flex-wrap gap-2"><Button variant="outline" size="sm" disabled={renewingId === item.installation_id || Boolean(item.integrity_failed_at) || Boolean(item.previous_token_valid_until && new Date(item.previous_token_valid_until).getTime() > Date.now())} onClick={() => void renew(item)}>{renewingId === item.installation_id ? "Renewing…" : "Renew for 30 days"}</Button><Button variant="destructive" size="sm" disabled={revokingId === item.installation_id} onClick={() => void revoke(item.installation_id)}><Ban className="mr-2 h-4 w-4" />{revokingId === item.installation_id ? "Recording…" : "Mark revoked"}</Button></div>}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
