'use client';

import { Globe2, Pause, Play, RefreshCw, Trash2 } from 'lucide-react';
import { type FormEvent, useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { apiFetch } from '@/lib/kodewavesApi';

import styles from './FilesWorkspace.module.css';

type WebsiteSource = {
  source_uuid: string;
  url: string;
  status: string;
  is_active: boolean;
  available_to_all_agents: boolean;
  refresh_interval_hours: number;
  max_pages: number;
  last_refreshed_at: string | null;
  last_error: string | null;
  version: number;
};

export default function WebsiteSources() {
  const [sources, setSources] = useState<WebsiteSource[]>([]);
  const [url, setUrl] = useState('');
  const [shareWithAgents, setShareWithAgents] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await apiFetch<{ sources: WebsiteSource[] }>('/knowledge-base/website-sources');
      setSources(response.sources);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load website sources');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!sources.some((source) => ['pending', 'crawling', 'indexing'].includes(source.status))) return;
    const timer = window.setInterval(() => { void load(); }, 5000);
    return () => window.clearInterval(timer);
  }, [load, sources]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!url.trim()) return;
    setBusy(true);
    try {
      await apiFetch<WebsiteSource>('/knowledge-base/website-sources', {
        method: 'POST',
        body: JSON.stringify({ url: url.trim(), refresh_interval_hours: 24, max_pages: 50, available_to_all_agents: shareWithAgents }),
      });
      setUrl('');
      setShareWithAgents(true);
      toast.success('Website added. Its pages are being indexed.');
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not add website');
    } finally {
      setBusy(false);
    }
  };

  const action = async (source: WebsiteSource, operation: 'refresh' | 'pause' | 'resume' | 'delete') => {
    setBusy(true);
    try {
      const method = operation === 'delete' ? 'DELETE' : 'POST';
      await apiFetch(operation === 'delete'
        ? `/knowledge-base/website-sources/${source.source_uuid}`
        : `/knowledge-base/website-sources/${source.source_uuid}/${operation}`, { method });
      await load();
      if (operation === 'refresh' || operation === 'resume') toast.success('Website refresh queued');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Website source update failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="grid gap-4 rounded-2xl border bg-card p-5 shadow-sm" aria-labelledby="website-sources-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="website-sources-title" className="flex items-center gap-2 text-lg font-semibold"><Globe2 className="h-5 w-5" /> Website sources</h2>
          <p className="mt-1 text-sm text-muted-foreground">Crawl public HTTPS pages into this organization’s knowledge base. Agents can attach the indexed document in their workflow.</p>
        </div>
      </div>
      <form className="flex flex-col gap-2 sm:flex-row" onSubmit={submit}>
        <Input type="url" inputMode="url" autoComplete="url" placeholder="https://www.example.com" value={url} onChange={(event) => setUrl(event.target.value)} aria-label="Website URL" required />
        <Button type="submit" disabled={busy || !url.trim()}>{busy ? 'Working…' : 'Add website'}</Button>
      </form>
      <label className="flex items-start gap-2 text-sm text-muted-foreground">
        <input type="checkbox" checked={shareWithAgents} onChange={(event) => setShareWithAgents(event.target.checked)} />
        Make this source available to all agents in this organization
      </label>
      <p className="text-xs text-muted-foreground">HTTPS only · up to 50 pages · 512 KiB per source · maximum 5 active sources per organization · refreshed daily · robots.txt is respected</p>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {loading ? <p className="text-sm text-muted-foreground">Loading website sources…</p> : sources.length === 0 ? (
        <p className="rounded-xl border border-dashed p-5 text-center text-sm text-muted-foreground">No website sources yet.</p>
      ) : (
        <div className="grid gap-2">
          {sources.map((source) => (
            <article key={source.source_uuid} className={styles.row}>
              <div className={styles.fileDetails}>
                <a className="truncate text-sm font-semibold underline-offset-4 hover:underline" href={source.url} target="_blank" rel="noreferrer">{source.url}</a>
                <div className={styles.fileMeta}>
                  <span>Status: {source.status}</span><span>Version {source.version}</span>
                  {source.available_to_all_agents && <span>Shared with organization agents</span>}
                  {source.last_refreshed_at && <span>Last indexed {new Date(source.last_refreshed_at).toLocaleString()}</span>}
                </div>
                {source.last_error && <p className="mt-2 text-xs text-destructive">{source.last_error}</p>}
              </div>
              <div className={styles.rowActions}>
                <Button variant="ghost" size="sm" disabled={busy || !source.is_active || source.status === 'paused'} onClick={() => void action(source, 'refresh')} aria-label="Refresh website"><RefreshCw className="h-4 w-4" /></Button>
                <Button variant="ghost" size="sm" disabled={busy || !source.is_active} onClick={() => void action(source, source.status === 'paused' ? 'resume' : 'pause')} aria-label={source.status === 'paused' ? 'Resume website refresh' : 'Pause website refresh'}>{source.status === 'paused' ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}</Button>
                <Button variant="ghost" size="sm" disabled={busy} onClick={() => void action(source, 'delete')} aria-label="Delete website source"><Trash2 className="h-4 w-4" /></Button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
