"use client";

import { Activity, CirclePause, CirclePlay, PackageCheck, RefreshCw, ShieldAlert, Square, Upload } from "lucide-react";
import { type FormEvent,useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/kodewavesApi";

import styles from "./InstallationsWorkspace.module.css";

type ReleaseState = "draft" | "published";
type RolloutState = "staged" | "active" | "paused" | "stopped" | "completed";
type UpdateState = "staged" | "downloading" | "applying" | "applied" | "failed" | "rolled_back";

interface ClientRelease {
  release_id: string;
  version: string;
  archive_url: string;
  archive_sha256: string;
  archive_signature: string;
  min_current_version: string;
  notes: string;
  state: ReleaseState;
  created_at: string;
  published_at: string | null;
}

interface RolloutTarget {
  installation_id: string;
  status: UpdateState;
  current_version: string | null;
  detail: string;
  last_reported_at: string | null;
}

interface ClientRollout {
  rollout_id: string;
  release_id: string;
  state: RolloutState;
  created_at: string;
  started_at: string | null;
  paused_at: string | null;
  stopped_at: string | null;
  completed_at: string | null;
  targets: RolloutTarget[];
}

export interface ReleaseInstallation {
  installation_id: string;
  customer_id: string;
  identity_enrolled?: boolean;
  expires_at: number;
  revoked_at: string | null;
  integrity_failed_at: string | null;
}

const RELEASE_FIELDS = [
  "release_id", "version", "archive_url", "archive_sha256", "archive_signature", "min_current_version", "notes",
].sort();

const ENVELOPE_EXAMPLE = JSON.stringify({
  release_id: "kodewaves-1.48.0",
  version: "1.48.0",
  archive_url: "https://downloads.example.com/kodewaves/client-1.48.0.tar.gz",
  archive_sha256: "<64-character-lowercase-sha256>",
  archive_signature: "<86-character-base64url-ed25519-signature>",
  min_current_version: "1.47.0",
  notes: "Security and maintenance update",
}, null, 2);

function readableError(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function timeLabel(value: string | null): string {
  if (!value) return "Not reported yet";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function parseReleaseList(value: unknown): ClientRelease[] {
  if (!Array.isArray(value) || value.some((item) =>
    !item || typeof item !== "object" || typeof item.release_id !== "string" || typeof item.version !== "string"
  )) {
    throw new Error("The server returned an unexpected release response. Refresh the page or contact the platform owner.");
  }
  return value as ClientRelease[];
}

function parseRolloutList(value: unknown): ClientRollout[] {
  if (!Array.isArray(value) || value.some((item) =>
    !item || typeof item !== "object" || typeof item.rollout_id !== "string" || !Array.isArray(item.targets)
  )) {
    throw new Error("The server returned an unexpected rollout response. Refresh the page or contact the platform owner.");
  }
  return value as ClientRollout[];
}

function releaseEnvelope(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Paste a JSON object containing the signed release metadata.");
  }
  const item = value as Record<string, unknown>;
  const keys = Object.keys(item).sort();
  if (JSON.stringify(keys) !== JSON.stringify(RELEASE_FIELDS)) {
    throw new Error("The envelope must contain only release_id, version, archive_url, archive_sha256, archive_signature, min_current_version and notes.");
  }
  if (Object.values(item).some((entry) => typeof entry !== "string")) {
    throw new Error("Every release envelope value must be a string.");
  }
  return item as Record<string, string>;
}

export function ClientReleaseControl({ installations }: { installations: ReleaseInstallation[] }) {
  const { user, loading: authLoading } = useAuth();
  const isOwner = !authLoading && user?.is_superuser === true;
  const [releases, setReleases] = useState<ClientRelease[]>([]);
  const [rollouts, setRollouts] = useState<ClientRollout[]>([]);
  const [envelopeJson, setEnvelopeJson] = useState("");
  const [selectedRelease, setSelectedRelease] = useState("");
  const [selectedInstallations, setSelectedInstallations] = useState<string[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const eligibleInstallations = useMemo(() => installations.filter((item) =>
    item.identity_enrolled === true && !item.revoked_at && !item.integrity_failed_at && item.expires_at * 1000 > Date.now()
  ), [installations]);

  const refresh = useCallback(async () => {
    if (!isOwner) return;
    setLoading(true);
    setError("");
    try {
      const [releaseResponse, rolloutResponse] = await Promise.all([
        apiFetch<unknown>("/admin/client-installations/releases"),
        apiFetch<unknown>("/admin/client-installations/rollouts"),
      ]);
      const nextReleases = parseReleaseList(releaseResponse);
      const nextRollouts = parseRolloutList(rolloutResponse);
      setReleases(nextReleases);
      setRollouts(nextRollouts);
      setSelectedRelease((current) => current || nextReleases.find((item) => item.state === "published")?.release_id || "");
    } catch (cause) {
      setError(readableError(cause, "Unable to load client releases and rollouts."));
    } finally {
      setLoading(false);
    }
  }, [isOwner]);

  useEffect(() => {
    if (isOwner && expanded) void refresh();
  }, [expanded, isOwner, refresh]);

  useEffect(() => {
    if (window.location.hash !== "#release-management") return;
    setExpanded(true);
    window.requestAnimationFrame(() => {
      document.getElementById("release-management")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, []);

  const createRelease = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy("create-release");
    setError("");
    setNotice("");
    try {
      let parsed: unknown;
      try {
        parsed = JSON.parse(envelopeJson);
      } catch {
        throw new Error("Release metadata must be valid JSON.");
      }
      const envelope = releaseEnvelope(parsed);
      const release = await apiFetch<ClientRelease>("/admin/client-installations/releases", {
        method: "POST",
        body: JSON.stringify(envelope),
      });
      setEnvelopeJson("");
      setSelectedRelease(release.release_id);
      setNotice(`Release ${release.version} saved as a draft. Publish it after reviewing the version and signed archive details.`);
      await refresh();
    } catch (cause) {
      setError(readableError(cause, "Unable to save the signed release."));
    } finally {
      setBusy(null);
    }
  };

  const publishRelease = async (release: ClientRelease) => {
    if (!window.confirm(`Publish immutable release ${release.version}? Published release metadata cannot be changed.`)) return;
    setBusy(`publish:${release.release_id}`);
    setError("");
    setNotice("");
    try {
      await apiFetch(`/admin/client-installations/releases/${encodeURIComponent(release.release_id)}/publish`, { method: "POST" });
      setNotice(`Release ${release.version} is published and available for staged rollouts.`);
      await refresh();
    } catch (cause) {
      setError(readableError(cause, "Unable to publish the release."));
    } finally {
      setBusy(null);
    }
  };

  const createRollout = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedRelease || selectedInstallations.length === 0) return;
    setBusy("create-rollout");
    setError("");
    setNotice("");
    try {
      const idempotencyKey = crypto.randomUUID().replaceAll("-", "");
      const result = await apiFetch<ClientRollout & { created?: boolean }>("/admin/client-installations/rollouts", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({ release_id: selectedRelease, installation_ids: selectedInstallations }),
      });
      setSelectedInstallations([]);
      setNotice(result.created === false ? "The matching rollout already exists; its existing status is shown below." : `Staged rollout ${result.rollout_id} for ${result.targets.length} installation${result.targets.length === 1 ? "" : "s"}. Activate it when ready to begin delivery.`);
      await refresh();
    } catch (cause) {
      setError(readableError(cause, "Unable to stage the rollout."));
    } finally {
      setBusy(null);
    }
  };

  const transitionRollout = async (rollout: ClientRollout, action: "activate" | "pause" | "stop") => {
    const confirmations: Record<typeof action, string> = {
      activate: `Activate rollout ${rollout.rollout_id} so its selected customer installations can receive the signed update?`,
      pause: `Pause rollout ${rollout.rollout_id}? No new update should be offered while paused.`,
      stop: `Stop rollout ${rollout.rollout_id}? Stopped rollouts cannot be resumed.`,
    };
    if (!window.confirm(confirmations[action])) return;
    setBusy(`${action}:${rollout.rollout_id}`);
    setError("");
    setNotice("");
    try {
      await apiFetch(`/admin/client-installations/rollouts/${encodeURIComponent(rollout.rollout_id)}/${action}`, { method: "POST" });
      setNotice(`Rollout ${rollout.rollout_id} ${action === "activate" ? "activated" : action === "pause" ? "paused" : "stopped"}.`);
      await refresh();
    } catch (cause) {
      setError(readableError(cause, `Unable to ${action} the rollout.`));
    } finally {
      setBusy(null);
    }
  };

  if (authLoading || !isOwner) return null;

  return (
    <section id="release-management" className="scroll-mt-6 grid gap-5" aria-labelledby="client-release-control-title">
      <Card className={styles.sectionCard}>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle id="client-release-control-title" className="flex items-center gap-2 text-base"><PackageCheck className="h-4 w-4" />Client releases and updates</CardTitle>
              <CardDescription className="mt-1 max-w-3xl">Publish owner-signed, immutable installation packages and stage an update for active, enrolled clients. The private release key stays offline and is never accepted by this page.</CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              {expanded && <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={loading || busy !== null}>
                <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />Refresh releases
              </Button>}
              <Button type="button" variant={expanded ? "outline" : "default"} size="sm" aria-expanded={expanded} aria-controls="client-release-controls" onClick={() => setExpanded((current) => !current)}>
                {expanded ? "Hide release controls" : "Manage releases and rollouts"}
              </Button>
            </div>
          </div>
        </CardHeader>
        {!expanded ? <CardContent className="pt-0 text-sm text-muted-foreground">Open release management when you need to publish a signed package or review staged client updates.</CardContent> : <CardContent id="client-release-controls" className="grid gap-6">
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(18rem,.8fr)]">
            <form className="grid content-start gap-3 rounded-xl border bg-background/60 p-4" onSubmit={(event) => void createRelease(event)}>
              <div>
                <h3 className="font-semibold">Add signed release</h3>
                <p className="mt-1 text-sm text-muted-foreground">Paste the already signed public envelope from the release process. The API verifies its Ed25519 signature before saving it as a draft.</p>
              </div>
              <Label htmlFor="client-release-envelope">Signed release envelope JSON</Label>
              <Textarea
                id="client-release-envelope"
                value={envelopeJson}
                onChange={(event) => setEnvelopeJson(event.target.value)}
                placeholder={ENVELOPE_EXAMPLE}
                rows={9}
                spellCheck={false}
                className="min-h-52 font-mono text-xs"
                required
              />
              <p className="text-xs text-muted-foreground">Expected fields: release ID, version, HTTPS archive URL, archive SHA-256, detached signature, minimum supported version and notes. Do not paste a private key.</p>
              <Button type="submit" disabled={busy !== null || !envelopeJson.trim()}><Upload className="mr-2 h-4 w-4" />{busy === "create-release" ? "Verifying…" : "Save release draft"}</Button>
            </form>

            <form className="grid content-start gap-3 rounded-xl border bg-background/60 p-4" onSubmit={(event) => void createRollout(event)}>
              <div>
                <h3 className="font-semibold">Stage a client rollout</h3>
                <p className="mt-1 text-sm text-muted-foreground">Only published releases and active enrolled installations are eligible. Staging does not deliver updates until you activate the rollout.</p>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="rollout-release">Published release</Label>
                <select id="rollout-release" value={selectedRelease} onChange={(event) => setSelectedRelease(event.target.value)} className="h-10 rounded-md border border-input bg-background px-3 text-sm" required>
                  <option value="">Choose a published release</option>
                  {releases.filter((release) => release.state === "published").map((release) => <option key={release.release_id} value={release.release_id}>{release.version} · {release.release_id}</option>)}
                </select>
              </div>
              <fieldset className="grid max-h-56 gap-2 overflow-auto rounded-lg border p-3">
                <legend className="px-1 text-sm font-medium">Enrolled target installations</legend>
                {eligibleInstallations.length === 0 ? <p className="text-sm text-muted-foreground">No active enrolled installations are eligible yet.</p> : eligibleInstallations.map((installation) => (
                  <label key={installation.installation_id} className="flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedInstallations.includes(installation.installation_id)}
                      onChange={(event) => setSelectedInstallations((current) => event.target.checked
                        ? [...current, installation.installation_id]
                        : current.filter((id) => id !== installation.installation_id))}
                      className="mt-1"
                    />
                    <span>{installation.customer_id} <span className="font-mono text-xs text-muted-foreground">({installation.installation_id})</span></span>
                  </label>
                ))}
              </fieldset>
              <Button type="submit" disabled={busy !== null || !selectedRelease || selectedInstallations.length === 0}>
                <Activity className="mr-2 h-4 w-4" />{busy === "create-rollout" ? "Staging…" : `Stage rollout${selectedInstallations.length ? ` for ${selectedInstallations.length}` : ""}`}
              </Button>
            </form>
          </div>

          {error && <p className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive" role="alert">{error}</p>}
          {notice && <p className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm" role="status">{notice}</p>}

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="grid content-start gap-3">
              <h3 className="font-semibold">Release catalog <span className="text-sm font-normal text-muted-foreground">({releases.length})</span></h3>
              {loading && <p className="text-sm text-muted-foreground" role="status">Loading signed releases…</p>}
              {!loading && releases.length === 0 && <p className={styles.empty}>No signed releases have been added.</p>}
              {releases.map((release) => <article key={release.release_id} className="grid gap-3 rounded-xl border bg-background/50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div><h4 className="font-semibold">v{release.version}</h4><p className="font-mono text-xs text-muted-foreground">{release.release_id}</p></div>
                  <span className="rounded-full border px-2.5 py-1 text-xs font-medium">{release.state}</span>
                </div>
                <p className="break-all text-xs text-muted-foreground">SHA-256: {release.archive_sha256}</p>
                {release.notes && <p className="text-sm">{release.notes}</p>}
                {release.state === "draft" && <Button type="button" variant="outline" size="sm" className="justify-self-start" disabled={busy !== null} onClick={() => void publishRelease(release)}>
                  <ShieldAlert className="mr-2 h-4 w-4" />{busy === `publish:${release.release_id}` ? "Publishing…" : "Review and publish"}
                </Button>}
              </article>)}
            </div>

            <div className="grid content-start gap-3">
              <h3 className="font-semibold">Rollout status <span className="text-sm font-normal text-muted-foreground">({rollouts.length})</span></h3>
              {loading && <p className="text-sm text-muted-foreground" role="status">Loading rollout status…</p>}
              {!loading && rollouts.length === 0 && <p className={styles.empty}>No client updates are staged.</p>}
              {rollouts.map((rollout) => {
                const release = releases.find((item) => item.release_id === rollout.release_id);
                const canActivate = rollout.state === "staged" || rollout.state === "paused";
                const canPause = rollout.state === "active";
                const canStop = ["staged", "active", "paused"].includes(rollout.state);
                return <article key={rollout.rollout_id} className="grid gap-3 rounded-xl border bg-background/50 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div><h4 className="font-semibold">{release ? `v${release.version}` : rollout.release_id}</h4><p className="font-mono text-xs text-muted-foreground">Rollout {rollout.rollout_id}</p></div>
                    <span className="rounded-full border px-2.5 py-1 text-xs font-medium">{rollout.state}</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {canActivate && <Button type="button" size="sm" disabled={busy !== null} onClick={() => void transitionRollout(rollout, "activate")}><CirclePlay className="mr-1.5 h-4 w-4" />Activate</Button>}
                    {canPause && <Button type="button" size="sm" variant="outline" disabled={busy !== null} onClick={() => void transitionRollout(rollout, "pause")}><CirclePause className="mr-1.5 h-4 w-4" />Pause</Button>}
                    {canStop && <Button type="button" size="sm" variant="destructive" disabled={busy !== null} onClick={() => void transitionRollout(rollout, "stop")}><Square className="mr-1.5 h-4 w-4" />Stop</Button>}
                  </div>
                  <div className="grid gap-2">
                    {rollout.targets.map((target) => <div key={target.installation_id} className="rounded-lg border px-3 py-2 text-xs">
                      <div className="flex flex-wrap justify-between gap-1"><span className="font-mono">{target.installation_id}</span><strong>{target.status}</strong></div>
                      <p className="mt-1 text-muted-foreground">Installed: {target.current_version || "unknown"} · Last update: {timeLabel(target.last_reported_at)}</p>
                      {target.detail && <p className="mt-1 break-words text-muted-foreground">{target.detail}</p>}
                    </div>)}
                  </div>
                </article>;
              })}
            </div>
          </div>
        </CardContent>}
      </Card>
    </section>
  );
}
