import { Suspense } from 'react';
import panel from "@/components/layout/PanelWorkspace.module.css";

import { getWorkflowsApiV1WorkflowFetchGet, listFoldersApiV1FolderGet } from '@/client/sdk.gen';
import type { FolderResponse, WorkflowListResponse } from '@/client/types.gen';
import { Card, CardContent } from '@/components/ui/card';
import { CreateWorkflowButton } from "@/components/workflow/CreateWorkflowButton";
import { EmptyWorkflowState } from '@/components/workflow/EmptyWorkflowState';
import { AgentFolderView } from '@/components/workflow/folders/AgentFolderView';
import { CreateFolderButton } from '@/components/workflow/folders/CreateFolderButton';
import { FolderSection } from '@/components/workflow/folders/FolderSection';
import { UploadWorkflowButton } from '@/components/workflow/UploadWorkflowButton';
import { getServerAccessToken, getServerAuthProvider } from '@/lib/auth/server';
import logger from '@/lib/logger';
import { detailFromError } from '@/lib/apiError';

import WorkflowLayout from "./WorkflowLayout";

export const dynamic = 'force-dynamic';

// Server component for workflow list
async function WorkflowList() {
    const authProvider = await getServerAuthProvider();
    const accessToken = await getServerAccessToken();

    if (!accessToken) {
        // If no token, user needs to sign in
        const { redirect } = await import('next/navigation');
        if (authProvider === 'stack') {
            redirect('/');
        } else {
            // For OSS mode, this shouldn't happen as token is auto-generated
            return (
                <div className="text-red-500">
                    Authentication required. Please refresh the page.
                </div>
            );
        }
    }

    try {
        // Fetch both active and archived workflows in a single request
        const response = await getWorkflowsApiV1WorkflowFetchGet({
            headers: {
                'Authorization': `Bearer ${accessToken}`,
            },
            query: {
                status: 'active,archived'
            }
        });

        if (response.error || !response.data) {
            throw new Error(detailFromError(response.error, 'Unable to load agents. Please retry.'));
        }

        const allWorkflowData = response.data ? (Array.isArray(response.data) ? response.data : [response.data]) : [];

        // Separate active and archived workflows
        const activeWorkflows = allWorkflowData
            .filter((w: WorkflowListResponse) => w.status === 'active')
            .sort((a: WorkflowListResponse, b: WorkflowListResponse) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

        const archivedWorkflows = allWorkflowData
            .filter((w: WorkflowListResponse) => w.status === 'archived')
            .sort((a: WorkflowListResponse, b: WorkflowListResponse) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

        // Fetch folders for grouping active agents. A failure here shouldn't
        // break the page — fall back to an empty list (flat, ungrouped view).
        let folders: FolderResponse[] = [];
        try {
            const foldersResponse = await listFoldersApiV1FolderGet({
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                },
            });
            folders = foldersResponse.data ?? [];
        } catch (folderErr) {
            logger.error(`Error fetching folders: ${folderErr}`);
        }

        return (
            <>
                {/* Active Workflows Section */}
                <section className="mb-10" aria-labelledby="active-agents-heading">
                    <div className="mb-5 flex flex-wrap items-end justify-between gap-3 border-b border-border pb-4">
                        <div>
                            <h2 id="active-agents-heading" className="text-xl font-semibold tracking-tight">Active agents</h2>
                            <p className="mt-1 text-sm text-muted-foreground">Organize workflows, make edits, and test before publishing.</p>
                        </div>
                        <div className="flex flex-wrap gap-2 text-xs">
                            <span className="rounded-full border border-border bg-card px-3 py-1.5 text-muted-foreground"><strong className="mr-1.5 font-semibold tabular-nums text-foreground">{activeWorkflows.length}</strong>active</span>
                            <span className="rounded-full border border-border bg-card px-3 py-1.5 text-muted-foreground"><strong className="mr-1.5 font-semibold tabular-nums text-foreground">{folders.length}</strong>folders</span>
                        </div>
                    </div>
                    {activeWorkflows.length > 0 || folders.length > 0 ? (
                        <AgentFolderView workflows={activeWorkflows} folders={folders} />
                    ) : (
                        <EmptyWorkflowState />
                    )}
                </section>

                {/* Archived Section — collapsible, same design as the folder/Uncategorized sections */}
                {archivedWorkflows.length > 0 && (
                    <div className="mb-8">
                        <FolderSection kind="archived" workflows={archivedWorkflows} />
                    </div>
                )}
            </>
        );
    } catch (err) {
        logger.error(`Error fetching workflows: ${err}`);
        return (
            <div role="alert" className="text-red-500">
                <p>{err instanceof Error ? err.message : 'Unable to load agents. Please retry.'}</p>
                <a className="underline" href="/workflow">Retry loading agents</a>
            </div>
        );
    }
}

async function PageContent() {

    const workflowList = await WorkflowList();

    return (
        <div className="container mx-auto px-4 py-8">
            {/* Your Workflows Section */}
            <div className="mb-6">
                <div className={panel.collectionHeader}>
                    <div><span className={panel.eyebrow}>BUILD / AGENT WORKFLOWS</span><h1>Your Agents</h1><p>Design conversations, connect business tools, and validate every workflow before it goes live.</p></div>
                    <div className="flex max-w-full flex-wrap items-center gap-2 [&>*]:max-w-full">
                        <UploadWorkflowButton />
                        <CreateFolderButton />
                        <CreateWorkflowButton />
                    </div>
                </div>
                {workflowList}
            </div>
        </div>
    );
}

function WorkflowsLoading() {
    return (
        <div className="container mx-auto px-4 py-8">
            {/* Get Started Section Loading */}
            <div className="mb-12">
                <div className="h-8 w-48 bg-muted rounded mb-6"></div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {Array.from({ length: 3 }, (_, i) => (
                        <Card key={i}>
                            <CardContent className="p-0">
                                <div className="h-40 bg-muted/70" />
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </div>

            {/* Your Workflows Section Loading */}
            <div className="mb-6">
                <div className="flex justify-between items-center mb-6">
                    <div className="h-8 w-48 bg-muted rounded"></div>
                    <div className="h-10 w-32 bg-muted rounded"></div>
                </div>
                <Card>
                    <CardContent className="p-0">
                        <div className="h-96 bg-muted/70" />
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}

export default function WorkflowPage() {
    return (
        <WorkflowLayout showFeaturesNav={true}>
            <Suspense fallback={<WorkflowsLoading />}>
                <PageContent />
            </Suspense>
        </WorkflowLayout>

    );
}
