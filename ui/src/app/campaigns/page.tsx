"use client";

import { ArrowUpRight, Megaphone, Plus, Search, Users, Workflow, Zap } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getCampaignsApiV1CampaignGet } from "@/client/sdk.gen";
import type { CampaignsResponse } from "@/client/types.gen";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useOrganizationTimezone } from "@/hooks/useOrganizationTimezone";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/dateTime";

const stateStyles: Record<string, string> = {
    running: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    completed: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    paused: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
    failed: "border-destructive/30 bg-destructive/10 text-destructive",
    created: "border-border bg-muted text-muted-foreground",
};

export default function CampaignsPage() {
    const { user, getAccessToken, redirectToLogin, loading } = useAuth();
    const organizationTimezone = useOrganizationTimezone();
    const router = useRouter();
    const [campaignsData, setCampaignsData] = useState<CampaignsResponse | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [retry, setRetry] = useState(0);
    const [search, setSearch] = useState("");
    const [stateFilter, setStateFilter] = useState("all");

    useEffect(() => {
        if (!loading && !user) redirectToLogin();
    }, [loading, user, redirectToLogin]);

    useEffect(() => {
        if (loading || !user) return;
        let cancelled = false;
        const fetchCampaigns = async () => {
            setIsLoading(true);
            setError(null);
            try {
                const accessToken = await getAccessToken();
                const response = await getCampaignsApiV1CampaignGet({ headers: { Authorization: `Bearer ${accessToken}` } });
                if (response.error) throw new Error(detailFromError(response.error, "Failed to load campaigns"));
                if (response.data && !cancelled) setCampaignsData(response.data);
            } catch (cause) {
                if (!cancelled) setError(cause instanceof Error ? cause.message : "Failed to load campaigns");
            } finally {
                if (!cancelled) setIsLoading(false);
            }
        };
        void fetchCampaigns();
        return () => { cancelled = true; };
    }, [loading, user, getAccessToken, retry]);

    const campaignRows = campaignsData?.campaigns ?? [];
    const query = search.trim().toLowerCase();
    const filteredCampaigns = campaignRows.filter((campaign) => {
        const matchesState = stateFilter === "all" || campaign.state === stateFilter;
        const matchesSearch = !query || campaign.name.toLowerCase().includes(query) || campaign.workflow_name.toLowerCase().includes(query);
        return matchesState && matchesSearch;
    });
    const runningCampaigns = campaignRows.filter((campaign) => campaign.state === "running").length;
    const completedCampaigns = campaignRows.filter((campaign) => campaign.state === "completed").length;
    const queuedCalls = campaignRows.reduce((total, campaign) => total + (campaign.total_queued_count ?? 0), 0);
    const createCampaign = () => router.push("/campaigns/new");

    return (
        <main className="mx-auto w-full max-w-screen-2xl space-y-7 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
            <section className="relative isolate overflow-hidden rounded-3xl border border-border bg-gradient-to-br from-card via-card to-primary/10 px-5 py-6 sm:px-8 sm:py-8">
                <div aria-hidden="true" className="absolute -right-12 -top-20 -z-10 h-64 w-64 rounded-full bg-primary/10 blur-3xl" />
                <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
                    <div className="max-w-2xl">
                        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-xs font-semibold uppercase tracking-[.16em] text-primary"><Megaphone className="h-3.5 w-3.5" /> Campaign studio</div>
                        <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">Campaigns</h1>
                        <p className="mt-2 text-sm leading-6 text-muted-foreground sm:text-base">Launch workflow-powered outreach, then follow every queued contact through completion.</p>
                    </div>
                    <Button onClick={createCampaign} className="h-11 w-full gap-2 shadow-sm sm:w-auto"><Plus className="h-4 w-4" /> Create campaign</Button>
                </div>
            </section>

            <section aria-label="Campaign overview" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                {[
                    { label: "All campaigns", value: campaignRows.length, note: "Across this workspace", icon: Megaphone, tone: "text-primary bg-primary/10" },
                    { label: "Running now", value: runningCampaigns, note: "Actively reaching contacts", icon: Zap, tone: "text-emerald-600 bg-emerald-500/10" },
                    { label: "Completed", value: completedCampaigns, note: "Finished campaign runs", icon: Workflow, tone: "text-emerald-600 bg-emerald-500/10" },
                    { label: "Contacts queued", value: queuedCalls, note: "Total scheduled outreach", icon: Users, tone: "text-amber-600 bg-amber-500/10" },
                ].map((metric) => <Card key={metric.label} className="rounded-2xl border-border/70 shadow-sm"><CardContent className="p-4 sm:p-5"><div className="flex items-start justify-between gap-2"><span className="text-xs font-medium text-muted-foreground sm:text-sm">{metric.label}</span><span className={`rounded-xl p-2 ${metric.tone}`}><metric.icon className="h-4 w-4" /></span></div><p className="mt-3 text-2xl font-semibold tabular-nums tracking-tight sm:text-3xl">{metric.value.toLocaleString()}</p><p className="mt-1 text-[11px] text-muted-foreground sm:text-xs">{metric.note}</p></CardContent></Card>)}
            </section>

            <Card className="overflow-hidden rounded-2xl border-border/70 shadow-sm">
                <CardHeader className="gap-4 border-b border-border/70 bg-muted/20 px-4 py-5 sm:flex-row sm:items-end sm:justify-between sm:px-6">
                    <div><CardTitle className="text-lg">Campaign activity</CardTitle><CardDescription className="mt-1">A live view of workflow, delivery state, and execution progress.</CardDescription></div>
                    <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
                        <label className="relative block flex-1 sm:w-64"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><Input aria-label="Search campaigns" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search campaigns or workflows" className="pl-9" /></label>
                        <select aria-label="Filter campaigns by state" value={stateFilter} onChange={(event) => setStateFilter(event.target.value)} className="h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground"><option value="all">All states</option>{[...new Set(campaignRows.map((campaign) => campaign.state))].sort().map((state) => <option key={state} value={state}>{state.charAt(0).toUpperCase() + state.slice(1)}</option>)}</select>
                    </div>
                </CardHeader>
                <CardContent className="p-0">
                    {isLoading ? <div className="grid gap-3 p-4 sm:grid-cols-2 sm:p-6">{[1, 2, 3, 4].map((item) => <div key={item} className="h-36 animate-pulse rounded-xl bg-muted" />)}</div> : error ? <div role="alert" className="m-4 rounded-xl border border-destructive/30 bg-destructive/5 p-5 text-sm text-destructive sm:m-6"><p>{error}</p><Button variant="outline" className="mt-4" onClick={() => setRetry((value) => value + 1)}>Retry</Button></div> : campaignRows.length === 0 ? <div className="px-5 py-14 text-center"><span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-primary/10 text-primary"><Megaphone className="h-5 w-5" /></span><h2 className="mt-4 font-semibold">No campaigns yet</h2><p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">Build your first campaign to start reaching contacts through a workflow.</p><Button onClick={createCampaign} variant="outline" className="mt-5 gap-2"><Plus className="h-4 w-4" /> Create your first campaign</Button></div> : filteredCampaigns.length === 0 ? <div className="px-5 py-12 text-center"><p className="font-medium">No campaigns match these filters</p><Button variant="link" className="mt-1" onClick={() => { setSearch(""); setStateFilter("all"); }}>Clear filters</Button></div> : <div className="grid gap-3 p-4 sm:grid-cols-2 sm:p-6 xl:grid-cols-3">
                        {filteredCampaigns.map((campaign) => {
                            const queued = campaign.total_queued_count ?? 0;
                            const completed = campaign.executed_count ?? 0;
                            const progress = queued > 0 ? Math.min(100, Math.round((completed / queued) * 100)) : 0;
                            const variants = campaign.traffic_split?.variants.length ?? 1;
                            return <button key={campaign.id} type="button" onClick={() => router.push(`/campaigns/${campaign.id}`)} className="group flex min-w-0 flex-col rounded-2xl border border-border bg-card p-4 text-left transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:p-5">
                                <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate text-base font-semibold tracking-tight">{campaign.name}</p><p className="mt-1 truncate text-sm text-muted-foreground">{campaign.workflow_name}{variants > 1 && <span> · {variants} variants</span>}</p></div><Badge variant="outline" className={`shrink-0 capitalize ${stateStyles[campaign.state] ?? ""}`}>{campaign.state}</Badge></div>
                                <div className="mt-6 flex items-end justify-between gap-3"><div><p className="text-xs text-muted-foreground">Contacts reached</p><p className="mt-1 font-semibold tabular-nums">{completed.toLocaleString()} <span className="font-normal text-muted-foreground">/ {queued.toLocaleString()}</span></p></div><span className="text-sm font-semibold tabular-nums text-primary">{queued ? `${progress}%` : "—"}</span></div>
                                <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label={`${campaign.name} progress`} aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}><div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progress}%` }} /></div>
                                <div className="mt-4 flex items-center justify-between border-t border-border/70 pt-3 text-xs text-muted-foreground"><span>Created {formatDate(campaign.created_at, organizationTimezone)}</span><span className="inline-flex items-center gap-1 font-medium text-foreground opacity-70 group-hover:opacity-100">View <ArrowUpRight className="h-3.5 w-3.5" /></span></div>
                            </button>;
                        })}
                    </div>}
                </CardContent>
            </Card>
        </main>
    );
}
