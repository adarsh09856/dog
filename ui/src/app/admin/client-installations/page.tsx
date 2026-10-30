"use client";

import { Activity, AlertTriangle, Ban, Clock3, KeyRound, Plus, RefreshCw, ShieldCheck } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/kodewavesApi";

import admin from "../AdminWorkspace.module.css";
import styles from "./InstallationsWorkspace.module.css";

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
  identity_enrolled?: boolean;
  enrollment_expires_at?: string | null;
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

interface EnrollmentToken {
  installation_id: string;
  enrollment_token: string;
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

interface BindingRequest {
  id: number;
  installation_id: string;
  customer_id: string;
  requested_domains: string[];
  requested_ip_ranges: string[];
  reason: string;
  status: "pending" | "approved" | "rejected";
  created_at: string;
}

const DEFAULT_FEATURES = "voice, telephony, campaigns, crm, appointments, forms, widgets, knowledge_base, billing";

export default function ClientInstallationsPage() {
  const { user, loading: authLoading } = useAuth();
  const [records, setRecords] = useState<InstallationRecord[]>([]);
  const [alerts, setAlerts] = useState<IntegrityAlert[]>([]);
  const [bindingRequests, setBindingRequests] = useState<BindingRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [renewingId, setRenewingId] = useState<string | null>(null);
  const [enrollingId, setEnrollingId] = useState<string | null>(null);
  const [resolvingBindingId, setResolvingBindingId] = useState<number | null>(null);
  const [recoveringBindingId, setRecoveringBindingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [signerUnavailable, setSignerUnavailable] = useState(false);
  const [issued, setIssued] = useState<IssuedLicense | null>(null);
  const [enrollment, setEnrollment] = useState<EnrollmentToken | null>(null);
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
  const now = Date.now();
  const protectedCount = records.filter((record) => !record.revoked_at && !record.integrity_failed_at && record.expires_at * 1000 > now).length;
  const riskCount = records.filter((record) => Boolean(record.revoked_at || record.integrity_failed_at || record.expires_at * 1000 <= now)).length;
  const pendingBindingCount = bindingRequests.filter((request) => request.status === "pending").length;

  const refresh = useCallback(async () => {
    try {
      setError("");
      const [nextRecords, nextAlerts, nextBindingRequests] = await Promise.all([
        apiFetch<InstallationRecord[]>("/admin/client-installations"),
        apiFetch<IntegrityAlert[]>("/admin/client-installations/alerts"),
        apiFetch<BindingRequest[]>("/admin/client-installations/binding-requests?include_resolved=true"),
      ]);
      setRecords(nextRecords);
      setAlerts(nextAlerts);
      setBindingRequests(nextBindingRequests);
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
      setSignerUnavailable(false);
      await refresh();
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Unable to issue license.";
      setSignerUnavailable(/owner license signer|signing key/i.test(message));
      setError(message);
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

  const createEnrollment = async (id: string) => {
    setEnrollingId(id);
    setEnrollment(null);
    setError("");
    try {
      const result = await apiFetch<EnrollmentToken>(
        `/admin/client-installations/${encodeURIComponent(id)}/enrollment-token`,
        { method: "POST" },
      );
      setEnrollment(result);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to issue enrollment token.");
    } finally {
      setEnrollingId(null);
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

  const createRequestedDomainChallenge = async (request: BindingRequest, requestedDomain: string) => {
    setChallengeBusy(true);
    setError("");
    setCustomerId(request.customer_id);
    setDomain(requestedDomain);
    setDomainVerified(false);
    try {
      setChallenge(await apiFetch<DomainChallenge>("/admin/client-installations/domain-challenges", {
        method: "POST",
        body: JSON.stringify({ customer_id: request.customer_id, domain: requestedDomain }),
      }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to create the requested domain challenge.");
    } finally {
      setChallengeBusy(false);
    }
  };

  const approveBindingRequest = async (requestId: number) => {
    setResolvingBindingId(requestId);
    setIssued(null);
    setError("");
    try {
      const result = await apiFetch<IssuedLicense>(
        "/admin/client-installations/binding-requests/" + requestId + "/approve",
        { method: "POST" },
      );
      setIssued(result);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to approve this binding request.");
    } finally {
      setResolvingBindingId(null);
    }
  };

  const rejectBindingRequest = async (requestId: number) => {
    setResolvingBindingId(requestId);
    setError("");
    try {
      await apiFetch("/admin/client-installations/binding-requests/" + requestId + "/reject", {
        method: "POST",
        body: JSON.stringify({ note: "" }),
      });
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to reject this binding request.");
    } finally {
      setResolvingBindingId(null);
    }
  };

  const recoverBindingToken = async (requestId: number) => {
    setRecoveringBindingId(requestId);
    setIssued(null);
    setError("");
    try {
      const result = await apiFetch<IssuedLicense>(
        "/admin/client-installations/binding-requests/" + requestId + "/recover-token",
        { method: "POST" },
      );
      setIssued(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to recover this approved license.");
    } finally {
      setRecoveringBindingId(null);
    }
  };

  return (
    <div className={`${admin.surface} ${styles.surface}`} data-area="DISTRIBUTION / INSTALLATIONS">
      <div className={admin.hero}>
        <div>
          <span className={admin.kicker}>OWNER CONTROL / SIGNED DISTRIBUTION</span>
          <h1 className={admin.title}>Client Installations</h1>
          <p className="mt-1 text-sm text-muted-foreground">Govern each signed customer deployment: prove its domain, bind its network, review integrity signals, and control renewal or revocation.</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />Refresh owner state
        </Button>
      </div>

      <section className={styles.portfolio} aria-label="Installation control summary">
        {[
          { label: "Protected installations", value: loading ? "—" : protectedCount, icon: ShieldCheck, risk: false },
          { label: "Binding approvals pending", value: loading ? "—" : pendingBindingCount, icon: Activity, risk: pendingBindingCount > 0 },
          { label: "Integrity incidents", value: loading ? "—" : alerts.length, icon: AlertTriangle, risk: alerts.length > 0 },
          { label: "Expired / revoked / blocked", value: loading ? "—" : riskCount, icon: Clock3, risk: riskCount > 0 },
        ].map(({ label, value, icon: Icon, risk }) => (
          <div key={label} className={styles.portfolioItem}>
            <span className={`${styles.portfolioIcon} ${risk ? styles.portfolioIconRisk : ""}`}><Icon size={17} aria-hidden="true" /></span>
            <div><p className={styles.portfolioLabel}>{label}</p><p className={styles.portfolioValue}>{value}</p></div>
          </div>
        ))}
      </section>

      <div className={`${admin.prerequisite} ${styles.signingNote}`} role="note">
        <KeyRound className="h-5 w-5 shrink-0" aria-hidden="true" />
        <div><strong>Owner signing prerequisite</strong><p>License issuance requires the owner server to have a private signing key configured. This page cannot verify that server setting in advance; issuance reports an error if it is missing.</p></div>
      </div>
      {signerUnavailable && <div className={admin.setupError} role="alert">Owner signing is unavailable. Configure <code>KODEWAVES_OWNER_LICENSE_SIGNING_KEY_FILE</code> on the owner API server, mount the private key readable by that service, then retry issuance. Keep the private key out of client bundles.</div>}

      <Card className={styles.issueCard}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base"><Plus className="h-4 w-4" />Issue installation license</CardTitle>
          <CardDescription>Verify DNS control for the licensed domain before issuance. The signing key stays on the owner server; the license token is shown only once.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={issue} className={`${styles.issueForm} grid gap-4 sm:grid-cols-2`}>
            <div className={`${admin.formSection} ${styles.step}`}><span>01 / Installation identity</span><p>Assign a stable ID and customer record before binding the license to a destination.</p></div>
            <div className={`${styles.field} space-y-2`}><Label htmlFor="installation-id">Installation ID</Label><Input id="installation-id" required minLength={3} maxLength={100} pattern="[A-Za-z0-9][A-Za-z0-9._:-]{2,99}" title="Use 3–100 letters, digits, dots, underscores, colons or hyphens, starting with a letter or digit." value={installationId} onChange={(event) => setInstallationId(event.target.value)} /></div>
            <div className={`${styles.field} space-y-2`}><Label htmlFor="customer-id">Customer ID</Label><Input id="customer-id" required value={customerId} onChange={(event) => { setCustomerId(event.target.value); setChallenge(null); setDomainVerified(false); }} /></div>
            <div className={`${admin.formSection} ${styles.step}`}><span>02 / Domain and network binding</span><p>Prove control of the hostname with DNS. Add an IP/CIDR restriction only for deployments with a stable egress address.</p></div>
            <div className={`${styles.field} space-y-2`}><Label htmlFor="domain">Licensed domain</Label><Input id="domain" required placeholder="client.example.com" value={domain} onChange={(event) => { setDomain(event.target.value); setChallenge(null); setDomainVerified(false); }} /></div>
            <div className="space-y-2 sm:col-span-2"><Button type="button" variant="outline" disabled={challengeBusy || !customerId.trim() || !domain.trim()} onClick={() => void createChallenge()}>{challengeBusy ? "Checking DNS…" : "Create DNS challenge"}</Button></div>
            {challenge && <div className={`${styles.challenge} space-y-2 rounded-lg border p-3 text-sm sm:col-span-2`}>
              <p>Add this TXT record to the domain. The challenge expires {new Date(challenge.expires_at * 1000).toLocaleString()}.</p>
              <p className="break-all"><strong>Name:</strong></p><p className={styles.challengeValue}>{challenge.record_name}</p>
              <p className="break-all"><strong>Value:</strong></p><p className={styles.challengeValue}>{challenge.record_value}</p>
              <Button type="button" variant="outline" disabled={challengeBusy || domainVerified} onClick={() => void verifyChallenge()}>{domainVerified ? "Domain verified" : challengeBusy ? "Checking DNS…" : "Verify DNS record"}</Button>
            </div>}
            <div className={`${styles.field} space-y-2`}><Label htmlFor="ip-ranges">Allowed server IP/CIDR, optional</Label><Input id="ip-ranges" placeholder="203.0.113.10" value={ipRanges} onChange={(event) => setIpRanges(event.target.value)} /></div>
            <div className={`${admin.formSection} ${styles.step}`}><span>03 / Entitlements and validity</span><p>Define the features and capacity enforced by this signed license.</p></div>
            <div className="space-y-2 sm:col-span-2"><Label htmlFor="features">Enabled features, comma separated</Label><Input id="features" value={features} onChange={(event) => setFeatures(event.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="max-calls">Maximum concurrent calls</Label><Input id="max-calls" type="number" min={1} required value={maxCalls} onChange={(event) => setMaxCalls(Number(event.target.value))} /></div>
            <div className="space-y-2"><Label htmlFor="max-seats">Maximum provisioned users, optional</Label><Input id="max-seats" type="number" min={1} value={maxSeats} onChange={(event) => setMaxSeats(event.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="max-workspaces">Maximum workspaces, optional</Label><Input id="max-workspaces" type="number" min={1} value={maxWorkspaces} onChange={(event) => setMaxWorkspaces(event.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="max-agents">Maximum provisioned agents, optional</Label><Input id="max-agents" type="number" min={0} value={maxAgents} onChange={(event) => setMaxAgents(event.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="max-campaigns">Maximum campaigns, optional</Label><Input id="max-campaigns" type="number" min={0} value={maxCampaigns} onChange={(event) => setMaxCampaigns(event.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="valid-days">Valid for days</Label><Input id="valid-days" type="number" min={1} required value={days} onChange={(event) => setDays(Number(event.target.value))} /></div>
            <div className={`${admin.formFooter} ${styles.formFooter}`}><span>The signed token is displayed once after issuance.</span><Button type="submit" disabled={submitting}>{submitting ? "Issuing…" : "Issue signed license"}</Button></div>
          </form>
        </CardContent>
      </Card>

      {error && <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
      {enrollment && <Card className={styles.sectionCard}>
        <CardHeader><CardTitle className="text-base">Enrollment token for {enrollment.installation_id}</CardTitle><CardDescription>Shown once; expires {new Date(enrollment.expires_at * 1000).toLocaleString()}. Share it privately with the installation operator. Creating another token invalidates this one.</CardDescription></CardHeader>
        <CardContent className="space-y-3"><div><Label htmlFor="enrollment-token">One-time enrollment token</Label><Input id="enrollment-token" readOnly value={enrollment.enrollment_token} className="font-mono text-xs" /></div><Button variant="outline" onClick={() => setEnrollment(null)}>I have saved the token</Button></CardContent>
      </Card>}
      {alerts.length > 0 && <Card className={styles.sectionCard}>
        <CardHeader><CardTitle className="flex items-center gap-2 text-base text-destructive"><Ban className="h-4 w-4" />Installation integrity alerts ({alerts.length})</CardTitle><CardDescription>These reports contain protected-file paths and hashes only. Acknowledging an alert does not re-enable the client installation.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          {alerts.map((alert) => <div key={alert.id} className={styles.alertCard}>
            <div className={styles.alertHeading}><strong>{alert.installation_id} · {alert.reason.replaceAll("_", " ")}</strong><span className="text-xs text-destructive">Blocked · review required</span></div>
            <div className={styles.alertMeta}>
              <div className={styles.metaCell}><span className={styles.metaLabel}>Changed component</span><span className={styles.metaValue}>{alert.component}</span></div>
              <div className={styles.metaCell}><span className={styles.metaLabel}>Expected SHA-256</span><span className={styles.metaValue}>{alert.expected_sha256 || (alert.reason === "added_file" ? "Not in signed manifest" : "Unavailable")}</span></div>
              <div className={styles.metaCell}><span className={styles.metaLabel}>Observed SHA-256</span><span className={styles.metaValue}>{alert.observed_sha256 || (alert.reason === "missing_file" ? "Missing" : "Unavailable")}</span></div>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">First seen {new Date(alert.first_seen_at).toLocaleString()} · Last seen {new Date(alert.last_seen_at).toLocaleString()} · {alert.occurrence_count} check{alert.occurrence_count === 1 ? "" : "s"}</p>
            <Button className="mt-2" type="button" variant="outline" size="sm" onClick={() => void acknowledgeAlert(alert.id)}>Acknowledge</Button>
          </div>)}
        </CardContent>
      </Card>}
      {bindingRequests.length > 0 && <Card className={styles.sectionCard}>
        <CardHeader>
          <CardTitle className="text-base">Domain and IP change requests ({bindingRequests.length})</CardTitle>
          <CardDescription>Verify control of every requested domain before approving. Approved binding licenses can be recovered by an owner without rotating them.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {bindingRequests.map((request) => <div key={request.id} className={styles.requestCard}>
            <div className={styles.requestHeading}>
              <strong>Request #{request.id} · {request.installation_id}</strong>
              <span className="text-xs text-muted-foreground">{request.status} · {new Date(request.created_at).toLocaleString()}</span>
            </div>
            <div className={styles.requestMeta}>
              <p><strong>Requested domains:</strong> {request.requested_domains.join(", ")}</p>
              <p><strong>Requested source IP/CIDR:</strong> {request.requested_ip_ranges.join(", ") || "No IP restriction"}</p>
              <p className={styles.requestReason}><strong>Customer reason:</strong> {request.reason}</p>
            </div>
            {request.status === "pending" && <div className={styles.requestActions}>
              {request.requested_domains.map((requestedDomain) => <Button
                key={requestedDomain}
                type="button"
                variant="outline"
                size="sm"
                disabled={challengeBusy || resolvingBindingId === request.id}
                onClick={() => void createRequestedDomainChallenge(request, requestedDomain)}
              >Create DNS challenge · {requestedDomain}</Button>)}
              <Button
                type="button"
                size="sm"
                disabled={resolvingBindingId === request.id}
                onClick={() => void approveBindingRequest(request.id)}
              >{resolvingBindingId === request.id ? "Approving…" : "Approve and issue token"}</Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={resolvingBindingId === request.id}
                onClick={() => void rejectBindingRequest(request.id)}
              >{resolvingBindingId === request.id ? "Saving…" : "Reject request"}</Button>
            </div>}
            {request.status === "approved" && <Button
              className="mt-3"
              type="button"
              size="sm"
              variant="outline"
              disabled={recoveringBindingId === request.id}
              onClick={() => void recoverBindingToken(request.id)}
            >{recoveringBindingId === request.id ? "Recovering…" : "Recover approved license"}</Button>}
          </div>)}
        </CardContent>
      </Card>}
      {issued && (
        <Card className={styles.secretCard}>
          <CardHeader><CardTitle className="flex items-center gap-2 text-base"><KeyRound className="h-4 w-4" />Issued: {issued.installation_id}</CardTitle><CardDescription>Copy these values into the client installation configuration. Binding-approval tokens can be recovered from their approved request without changing the license.</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            <div className={styles.secretWarning}><KeyRound size={15} aria-hidden="true" /><p>This signed credential is displayed only after the owner action that issued or recovered it. Save it securely now; it will not be listed in installation metadata.</p></div>
            <div><Label htmlFor="issued-token">Signed license token</Label><textarea id="issued-token" readOnly value={issued.token} className={styles.secretField} /></div>
            <div><Label htmlFor="issued-public-key">Public verification key</Label><Input id="issued-public-key" readOnly value={issued.public_key} className="font-mono text-xs" /></div>
            <Button variant="outline" onClick={() => setIssued(null)}>I have saved the token</Button>
          </CardContent>
        </Card>
      )}

      <Card className={styles.sectionCard}>
        <CardHeader>
          <div className={styles.installationsHeading}>
            <div><CardTitle className="text-base">Issued installations</CardTitle><CardDescription>Owner metadata only; signed license tokens are not stored in this registry. Identity enrollment requires the approved client release to prove its bound key on owner checks.</CardDescription></div>
            <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={loading}><RefreshCw className={loading ? "mr-2 h-4 w-4 animate-spin" : "mr-2 h-4 w-4"} />Refresh</Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading && <p className={styles.empty} role="status">Loading installations…</p>}
          {!loading && records.length === 0 && <p className={styles.empty}>No installations issued yet.</p>}
          <div className={styles.installList}>
            {records.map((item) => {
              const expired = item.expires_at * 1000 <= now;
              const handoverActive = Boolean(item.previous_token_valid_until && new Date(item.previous_token_valid_until).getTime() > now);
              const statusClass = item.revoked_at || item.integrity_failed_at
                ? styles.stateBad
                : expired ? styles.stateWarn : styles.stateGood;
              const installClass = item.revoked_at
                ? styles.installationRevoked
                : item.integrity_failed_at
                  ? styles.installationUnsafe
                  : expired ? styles.installationExpired : "";
              return (
                <article key={item.installation_id} className={[styles.installation, installClass].filter(Boolean).join(" ")}>
                  <header className={styles.installationHead}>
                    <div className={styles.installationIdentity}><strong>{item.installation_id}</strong><span>Customer · {item.customer_id}</span></div>
                    <div className={styles.stateGroup}>
                      <span className={[styles.stateBadge, statusClass].join(" ")}>{item.revoked_at ? "Revoked" : item.integrity_failed_at ? "Integrity blocked" : expired ? "Expired" : "License active"}</span>
                      <span className={[styles.stateBadge, item.identity_enrolled ? styles.stateGood : styles.stateWarn].join(" ")}>{item.identity_enrolled ? "Identity enrolled" : "Identity not enrolled"}</span>
                    </div>
                  </header>
                  <div className={styles.dataGrid}>
                    <div className={styles.dataCell}><span className={styles.dataLabel}>Licensed domain</span><span className={styles.dataValue}>{item.domains.join(", ")}</span></div>
                    <div className={styles.dataCell}><span className={styles.dataLabel}>Allowed source IP/CIDR</span><span className={styles.dataValue}>{item.ip_ranges.join(", ") || "No IP restriction"}</span></div>
                    <div className={styles.dataCell}><span className={styles.dataLabel}>License expires</span><span className={styles.dataValue}>{new Date(item.expires_at * 1000).toLocaleString()}</span></div>
                    <div className={styles.dataCell}><span className={styles.dataLabel}>Enabled features</span><span className={styles.dataValue}>{item.features.join(", ") || "No features"}</span></div>
                    <div className={styles.dataCell}><span className={styles.dataLabel}>Concurrent call cap</span><span className={styles.dataValue}>{item.limits.max_concurrent_calls ?? 0}</span></div>
                    <div className={styles.dataCell}><span className={styles.dataLabel}>Provisioning caps</span><span className={styles.dataValue}>{item.limits.max_seats ?? "unlimited"} users · {item.limits.max_workspaces ?? "unlimited"} workspaces · {item.limits.max_agents ?? "unlimited"} agents · {item.limits.max_campaigns ?? "unlimited"} campaigns</span></div>
                    <div className={styles.dataCell}><span className={styles.dataLabel}>Owner check</span><span className={styles.dataValue}>{item.last_seen_at ? "Last owner check " + new Date(item.last_seen_at).toLocaleString() : "No client check received"}</span></div>
                    <div className={styles.dataCell}><span className={styles.dataLabel}>Installation identity</span><span className={styles.dataValue}>{item.identity_enrolled ? "Installation identity enrolled" : "Installation identity not enrolled"}{!item.identity_enrolled && item.enrollment_expires_at ? " · Token expires " + new Date(item.enrollment_expires_at).toLocaleString() : ""}</span></div>
                    {item.observed_ip && <div className={styles.dataCell}><span className={styles.dataLabel}>Last observed source IP</span><span className={[styles.dataValue, styles.dataMono].join(" ")}>{item.observed_ip}</span></div>}
                    {item.renewed_at && <div className={styles.dataCell}><span className={styles.dataLabel}>Last renewed</span><span className={styles.dataValue}>{new Date(item.renewed_at).toLocaleString()}</span></div>}
                    {handoverActive && <div className={styles.dataCell}><span className={styles.dataLabel}>Previous token handover</span><span className={[styles.dataValue, styles.handover].join(" ")}>Ends {new Date(item.previous_token_valid_until!).toLocaleString()}</span></div>}
                  </div>
                  {item.integrity_failed_at && <div className={[admin.setupError, styles.integrityBlock].join(" ")}><p className="font-semibold">Integrity alert received {new Date(item.integrity_failed_at).toLocaleString()}.</p><p className="mt-1">This installation is blocked and cannot be renewed. Preserve the incident, restore a clean approved release, and issue a replacement with a new installation ID. Acknowledgment records review only.</p></div>}
                  {item.revoked_at ? (
                    <p className={styles.revokedNotice}>Marked revoked {new Date(item.revoked_at).toLocaleString()}. The client applies this after its next successful owner check.</p>
                  ) : (
                    <div className={styles.installationActions}>
                      <Button variant="outline" size="sm" disabled={enrollingId === item.installation_id || Boolean(item.identity_enrolled) || Boolean(item.integrity_failed_at) || expired} onClick={() => void createEnrollment(item.installation_id)}>{enrollingId === item.installation_id ? "Creating…" : "Create enrollment token"}</Button>
                      <Button variant="outline" size="sm" disabled={renewingId === item.installation_id || Boolean(item.integrity_failed_at) || handoverActive} onClick={() => void renew(item)}>{renewingId === item.installation_id ? "Renewing…" : "Renew for 30 days"}</Button>
                      <Button variant="destructive" size="sm" disabled={revokingId === item.installation_id} onClick={() => void revoke(item.installation_id)}><Ban className="mr-2 h-4 w-4" />{revokingId === item.installation_id ? "Recording…" : "Mark revoked"}</Button>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
