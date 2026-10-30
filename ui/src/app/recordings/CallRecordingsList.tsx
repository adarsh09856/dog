"use client";

import { Headphones, Loader2, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { getUsageHistoryApiV1OrganizationsUsageRunsGet } from "@/client/sdk.gen";
import type { WorkflowRunUsageResponse } from "@/client/types.gen";
import { MediaPreviewDialog } from "@/components/MediaPreviewDialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useOrganizationTimezone } from "@/hooks/useOrganizationTimezone";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/dateTime";

const PAGE_SIZE = 50;

function formatDuration(seconds: number) {
    const wholeSeconds = Math.max(0, Math.floor(seconds));
    const minutes = Math.floor(wholeSeconds / 60);
    return `${minutes}:${String(wholeSeconds % 60).padStart(2, "0")}`;
}

function availableTracks(run: WorkflowRunUsageResponse) {
    if (run.recording_url) return [{ label: "Full call", url: run.recording_url }];
    return [
        run.user_recording_url ? { label: "Caller", url: run.user_recording_url } : null,
        run.bot_recording_url ? { label: "Agent", url: run.bot_recording_url } : null,
    ].filter((track): track is { label: string; url: string } => track !== null);
}

export default function CallRecordingsList() {
    const { isAuthenticated, loading: authLoading } = useAuth();
    const timezone = useOrganizationTimezone();
    const [runs, setRuns] = useState<WorkflowRunUsageResponse[]>([]);
    const [totalCount, setTotalCount] = useState(0);
    const [page, setPage] = useState(1);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const mediaPreview = MediaPreviewDialog();

    const fetchRuns = useCallback(async () => {
        if (!isAuthenticated) return;
        setLoading(true);
        setError(null);
        try {
            const response = await getUsageHistoryApiV1OrganizationsUsageRunsGet({
                query: { page, limit: PAGE_SIZE, sort_order: "desc" },
            });
            if (response.error || !response.data) {
                setError(detailFromError(response.error, "Could not load call recordings."));
                setRuns([]);
                setTotalCount(0);
                return;
            }
            setRuns(response.data.runs);
            setTotalCount(response.data.total_count);
        } catch (fetchError) {
            setError(detailFromError(fetchError, "Could not load call recordings."));
            setRuns([]);
            setTotalCount(0);
        } finally {
            setLoading(false);
        }
    }, [isAuthenticated, page]);

    useEffect(() => {
        if (authLoading) return;
        void fetchRuns();
    }, [authLoading, fetchRuns]);

    if (authLoading || (loading && runs.length === 0 && !error)) {
        return <div className="grid gap-3" aria-label="Loading call recordings">
            {[1, 2, 3].map((item) => <div key={item} className="flex items-center justify-between gap-4 rounded-xl border border-border p-4">
                <div className="flex-1 space-y-2"><Skeleton className="h-4 w-48" /><Skeleton className="h-3 w-64" /></div>
                <Skeleton className="h-8 w-24" />
            </div>)}
        </div>;
    }

    const recordings = runs.filter((run) => availableTracks(run).length > 0);
    const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

    return <div className="grid gap-3">
        {mediaPreview.dialog}
        <div className="flex items-center gap-3">
            <p className="min-w-0 flex-1 text-sm text-muted-foreground">
                {recordings.length} recording{recordings.length === 1 ? "" : "s"} on this page · {totalCount} completed calls checked
            </p>
            <Button variant="outline" size="icon" aria-label="Refresh call recordings" onClick={() => void fetchRuns()} disabled={loading}>
                <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            </Button>
        </div>

        {error ? <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">{error}</div> : recordings.length === 0 ? (
            <div className="grid justify-items-center gap-2 rounded-xl border border-dashed border-border p-10 text-center text-muted-foreground">
                <span className="grid size-11 place-items-center rounded-xl bg-muted"><Headphones className="h-5 w-5" /></span>
                <p className="font-medium text-foreground">No call recordings on this page</p>
                <p className="max-w-lg text-sm">Only calls saved with recording audio appear here. You can still review call details and transcripts from Agent Runs or Usage.</p>
            </div>
        ) : <div className="grid gap-3">
            {recordings.map((run) => {
                const tracks = availableTracks(run);
                const direction = run.call_type || (run.mode === "telephony" ? "Phone call" : "Browser call");
                const counterpart = run.call_type === "inbound" ? run.caller_number : run.called_number;
                return <article key={run.id} className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-4">
                    <div className="min-w-0 flex-1">
                        <p className="truncate font-medium text-foreground">{run.workflow_name || run.name || "Untitled agent"}</p>
                        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                            <span>Run #{run.id}</span>
                            <span>{direction}</span>
                            {counterpart && <span>{counterpart}</span>}
                            <span>{formatDateTime(run.created_at, timezone)}</span>
                            <span>{formatDuration(run.call_duration_seconds)}</span>
                        </div>
                    </div>
                    <div className="flex shrink-0 flex-wrap justify-end gap-2">
                        {tracks.map((track) => <Button key={track.label} variant="outline" size="sm"
                            aria-label={`Play ${track.label.toLowerCase()} recording for run ${run.id}`}
                            onClick={() => mediaPreview.openPreview(track.url, run.transcript_url ?? null, run.id)}>
                            <Headphones className="mr-2 h-4 w-4" />{track.label}
                        </Button>)}
                    </div>
                </article>;
            })}
        </div>}

        {totalPages > 1 && <div className="flex items-center justify-between gap-3">
            <span className="text-sm text-muted-foreground">Page {page} of {totalPages}</span>
            <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</Button>
                <Button variant="outline" size="sm" disabled={page >= totalPages || loading} onClick={() => setPage((value) => value + 1)}>Next</Button>
            </div>
        </div>}
        {loading && runs.length > 0 && <span className="sr-only"><Loader2 className="animate-spin" />Refreshing call recordings</span>}
    </div>;
}
