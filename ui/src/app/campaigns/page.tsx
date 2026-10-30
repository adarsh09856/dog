"use client";
import panel from "@/components/layout/PanelWorkspace.module.css";

import { Plus } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { getCampaignsApiV1CampaignGet } from '@/client/sdk.gen';
import type { CampaignsResponse } from '@/client/types.gen';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { useOrganizationTimezone } from '@/hooks/useOrganizationTimezone';
import { useAuth } from '@/lib/auth';
import { detailFromError } from '@/lib/apiError';
import { formatDate } from '@/lib/dateTime';

export default function CampaignsPage() {
    const { user, getAccessToken, redirectToLogin, loading } = useAuth();
    const organizationTimezone = useOrganizationTimezone();
    const router = useRouter();

    const [campaignsData, setCampaignsData] = useState<CampaignsResponse | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [retry, setRetry] = useState(0);

    // Redirect if not authenticated
    useEffect(() => {
        if (!loading && !user) {
            redirectToLogin();
        }
    }, [loading, user, redirectToLogin]);

    // Fetch campaigns once when user is ready
    useEffect(() => {
        if (loading || !user) {
            return;
        }
        let cancelled = false;

        const fetchCampaigns = async () => {
            setIsLoading(true);
            setError(null);
            try {
                const accessToken = await getAccessToken();
                const response = await getCampaignsApiV1CampaignGet({
                    headers: {
                        'Authorization': `Bearer ${accessToken}`,
                    }
                });

                if (response.error) throw new Error(detailFromError(response.error, 'Failed to load campaigns'));
                if (response.data && !cancelled) {
                    setCampaignsData(response.data);
                }
            } catch (error) {
                if (!cancelled) setError(error instanceof Error ? error.message : 'Failed to load campaigns');
            } finally {
                if (!cancelled) setIsLoading(false);
            }
        };

        fetchCampaigns();
        return () => { cancelled = true; };
    }, [loading, user, getAccessToken, retry]);

    const handleRowClick = (campaignId: number) => {
        router.push(`/campaigns/${campaignId}`);
    };

    const handleCreateCampaign = () => {
        router.push('/campaigns/new');
    };

    const campaignRows = campaignsData?.campaigns ?? [];
    const runningCampaigns = campaignRows.filter((campaign) => campaign.state === 'running').length;
    const completedCampaigns = campaignRows.filter((campaign) => campaign.state === 'completed').length;
    const queuedCalls = campaignRows.reduce((total, campaign) => total + (campaign.total_queued_count ?? 0), 0);

    const getStateBadgeVariant = (state: string) => {
        switch (state) {
            case 'created':
                return 'secondary';
            case 'running':
                return 'default';
            case 'paused':
                return 'outline';
            case 'completed':
                return 'secondary';
            case 'failed':
                return 'destructive';
            default:
                return 'secondary';
        }
    };

    return (
        <div className="container mx-auto max-w-screen-2xl px-4 py-7 sm:px-6 lg:px-8">
            <div className={panel.collectionHeader}>
                <div>
                    <span className={panel.eyebrow}>CHANNELS / CAMPAIGNS</span>
                    <h1>Campaigns</h1>
                    <p>Run workflows across a contact list and track progress from one place.</p>
                </div>
                <Button onClick={handleCreateCampaign}>
                    <Plus className="h-4 w-4 mr-2" />
                    Create Campaign
                </Button>
            </div>

            {!isLoading && !error && campaignsData && (
                <section aria-label="Campaign overview" className="mb-7 grid grid-cols-2 overflow-hidden rounded-xl border border-border bg-card sm:grid-cols-4">
                    {[
                        { label: 'Campaigns', value: campaignRows.length },
                        { label: 'Running now', value: runningCampaigns },
                        { label: 'Completed', value: completedCampaigns },
                        { label: 'Contacts queued', value: queuedCalls },
                    ].map((metric, index) => (
                        <div key={metric.label} className={`border-border p-4 sm:p-5 ${index % 2 === 0 ? 'border-r' : ''} ${index < 3 ? 'sm:border-r' : ''} ${index < 2 ? 'border-b sm:border-b-0' : ''}`}>
                            <p className="text-[10px] font-semibold uppercase tracking-[.13em] text-muted-foreground">{metric.label}</p>
                            <p className="mt-2 text-2xl font-semibold tracking-tight tabular-nums text-foreground">{metric.value.toLocaleString()}</p>
                        </div>
                    ))}
                </section>
            )}

                <Card className="overflow-hidden rounded-xl border-border shadow-sm">
                    <CardHeader>
                        <CardTitle>Campaign activity</CardTitle>
                        <CardDescription>
                            View current state, workflow and execution progress.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {isLoading ? (
                            <div className="animate-pulse space-y-3">
                                {[...Array(5)].map((_, i) => (
                                    <div key={i} className="h-12 bg-muted rounded"></div>
                                ))}
                            </div>
                        ) : error ? (
                            <div role="alert" className="space-y-3 text-destructive">
                                <p>{error}</p>
                                <Button variant="outline" onClick={() => setRetry(value => value + 1)}>Retry</Button>
                            </div>
                        ) : campaignsData && campaignsData.campaigns.length > 0 ? (
                            <div className="overflow-x-auto">
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>ID</TableHead>
                                            <TableHead>Name</TableHead>
                                            <TableHead>Workflow</TableHead>
                                            <TableHead>State</TableHead>
                                            <TableHead>Progress</TableHead>
                                            <TableHead>Created</TableHead>
                                            <TableHead className="text-right">Action</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {campaignsData.campaigns.map((campaign) => (
                                            <TableRow
                                                key={campaign.id}
                                                className="cursor-pointer transition-colors hover:bg-muted/50"
                                                onClick={() => handleRowClick(campaign.id)}
                                            >
                                                <TableCell>{campaign.id}</TableCell>
                                                <TableCell className="font-medium">{campaign.name}</TableCell>
                                                <TableCell>{campaign.workflow_name}{(campaign.traffic_split?.variants.length ?? 1) > 1 && <span className="text-muted-foreground"> +{(campaign.traffic_split?.variants.length ?? 1) - 1}</span>}</TableCell>
                                                <TableCell>
                                                    <Badge variant={getStateBadgeVariant(campaign.state)}>
                                                        {campaign.state}
                                                    </Badge>
                                                </TableCell>
                                                <TableCell>
                                                    <div className="min-w-28 space-y-1.5">
                                                        <div className="flex justify-between gap-3 text-xs tabular-nums">
                                                            <span>{campaign.executed_count ?? 0} / {campaign.total_queued_count ?? 0}</span>
                                                            <span className="text-muted-foreground">{(campaign.total_queued_count ?? 0) > 0 ? `${Math.min(100, Math.round(((campaign.executed_count ?? 0) / (campaign.total_queued_count ?? 1)) * 100))}%` : '—'}</span>
                                                        </div>
                                                        <div className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                                                            <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${(campaign.total_queued_count ?? 0) > 0 ? Math.min(100, ((campaign.executed_count ?? 0) / (campaign.total_queued_count ?? 1)) * 100) : 0}%` }} />
                                                        </div>
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    {formatDate(campaign.created_at, organizationTimezone)}
                                                </TableCell>
                                                <TableCell className="text-right">
                                                    <Button
                                                        variant="outline"
                                                        size="sm"
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            handleRowClick(campaign.id);
                                                        }}
                                                    >
                                                        View
                                                    </Button>
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>
                        ) : (
                            <div className="text-center py-8">
                                <p className="mb-4">No campaigns found</p>
                                <Button onClick={handleCreateCampaign} variant="outline">
                                    <Plus className="h-4 w-4 mr-2" />
                                    Create your first campaign
                                </Button>
                            </div>
                        )}
                    </CardContent>
                </Card>
        </div>
    );
}
