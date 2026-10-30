'use client';

import { useParams, useSearchParams } from 'next/navigation';
import { AlertTriangle, ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import posthog from 'posthog-js';
import { useEffect, useMemo, useState } from 'react';

import RenderWorkflow from '@/app/workflow/[workflowId]/RenderWorkflow';
import { getWorkflowApiV1WorkflowFetchWorkflowIdGet, getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet } from '@/client/sdk.gen';
import type { WorkflowResponse, WorkflowVersionResponse } from '@/client/types.gen';
import { FlowEdge, FlowNode } from '@/components/flow/types';
import SpinLoader from '@/components/SpinLoader';
import { PostHogEvent } from '@/constants/posthog-events';
import { detailFromError } from '@/lib/apiError';
import { useAuth } from '@/lib/auth';
import logger from '@/lib/logger';
import { WorkflowConfigurations } from '@/types/workflow-configurations';
import { Button } from '@/components/ui/button';

import WorkflowLayout from '../WorkflowLayout';

export default function WorkflowDetailPage() {
    const params = useParams();
    const searchParams = useSearchParams();
    const workflowId = Number(params.workflowId);
    const version = searchParams.get('version');
    const requestKey = `${workflowId}:${version ?? 'current'}`;
    const [loaded, setLoaded] = useState<{
        key: string;
        workflow: WorkflowResponse;
        version?: WorkflowVersionResponse;
    }>();
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const { user, redirectToLogin, loading: authLoading } = useAuth();

    // Redirect if not authenticated
    useEffect(() => {
        if (!authLoading && !user) {
            redirectToLogin();
        }
    }, [authLoading, user, redirectToLogin]);

    useEffect(() => {
        if (authLoading || !user) return;
        let cancelled = false;
        setLoading(true);
        setError(null);
        const fetchWorkflow = async () => {
            try {
                if (version !== null && version !== 'latest' && (
                    !/^[1-9]\d*$/.test(version) || !Number.isSafeInteger(Number(version))
                )) {
                    setError('Invalid workflow version. Use a version number or “latest”.');
                    return;
                }
                const [response, versionResponse] = await Promise.all([
                    getWorkflowApiV1WorkflowFetchWorkflowIdGet({
                        path: { workflow_id: workflowId },
                    }),
                    version === null ? Promise.resolve(null) : getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet({
                        path: { workflow_id: workflowId },
                        query: version === 'latest'
                            ? { status: 'published', limit: 1 }
                            : { version_number: Number(version), limit: 1 },
                    }),
                ]);
                if (cancelled) return;

                if (response.error) {
                    const fallback = response.response?.status === 503
                        ? 'Service is temporarily unavailable. Please try again later.'
                        : 'Failed to fetch workflow';
                    setError(detailFromError(response.error, fallback));
                    return;
                }

                const workflow = response.data;
                if (!workflow) {
                    setError('Workflow not found');
                    return;
                }
                if (versionResponse?.error) {
                    setError(detailFromError(versionResponse.error, 'Failed to fetch workflow version'));
                    return;
                }
                const selectedVersion = versionResponse?.data?.[0];
                if (version !== null && !selectedVersion) {
                    setError('Workflow version not found');
                    return;
                }
                setLoaded({ key: requestKey, workflow, version: selectedVersion });
                posthog.capture(PostHogEvent.WORKFLOW_EDITOR_OPENED, {
                    workflow_id: workflow.id,
                    workflow_name: workflow.name,
                });
            } catch (err) {
                if (!cancelled) setError('Failed to fetch workflow');
                logger.error(`Error fetching workflow: ${err}`);
            } finally {
                if (!cancelled) setLoading(false);
            }
        };

        void fetchWorkflow();
        return () => { cancelled = true; };
    }, [workflowId, version, requestKey, user, authLoading]);

    const stableUser = useMemo(() => user, [user]);
    const openTesterOnLoad = searchParams.get('onboarding') === 'web_call';
    const workflow = loaded?.key === requestKey ? loaded.workflow : undefined;
    const selectedVersion = loaded?.key === requestKey ? loaded.version : undefined;
    const definition = selectedVersion ? selectedVersion.workflow_json : workflow?.workflow_definition;
    const configurations = selectedVersion ? selectedVersion.workflow_configurations : workflow?.workflow_configurations;
    const templateVariables = selectedVersion ? selectedVersion.template_context_variables : workflow?.template_context_variables;

    if (authLoading || loading || (!error && loaded?.key !== requestKey)) {
        return (
            <WorkflowLayout>
                <SpinLoader />
            </WorkflowLayout>
        );
    }
    else if (error || !workflow) {
        return (
            <WorkflowLayout showFeaturesNav={false}>
                <main className="flex min-h-[65vh] items-center justify-center px-4 py-10 sm:px-6">
                    <section
                        aria-labelledby="workflow-unavailable-title"
                        className="w-full max-w-xl rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8"
                    >
                        <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-destructive/10 text-destructive">
                            <AlertTriangle className="h-5 w-5" aria-hidden="true" />
                        </div>
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                            Build / Voice agents
                        </p>
                        <h1 id="workflow-unavailable-title" className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
                            Agent editor unavailable
                        </h1>
                        <p role="alert" className="mt-3 text-sm leading-6 text-muted-foreground">
                            {error || 'Workflow not found'}
                        </p>
                        <div className="mt-6 flex flex-wrap gap-3">
                            <Button asChild>
                                <Link href="/workflow">
                                    <ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" />
                                    Back to agents
                                </Link>
                            </Button>
                        </div>
                    </section>
                </main>
            </WorkflowLayout>
        );
    }
    else {
        return stableUser ? (
            <RenderWorkflow
                key={requestKey}
                initialWorkflowName={workflow.name}
                workflowId={workflow.id}
                workflowUuid={workflow.workflow_uuid ?? undefined}
                initialTotalRuns={workflow.total_runs ?? 0}
                openTesterOnLoad={openTesterOnLoad}
                initialFlow={{
                    nodes: definition?.nodes as FlowNode[],
                    edges: definition?.edges as FlowEdge[],
                    viewport: { x: 0, y: 0, zoom: 0 }
                }}
                initialSelectedVersion={selectedVersion}
                initialTemplateContextVariables={templateVariables as Record<string, string> || {}}
                initialWorkflowConfigurations={
                    configurations
                        ? (configurations as WorkflowConfigurations)
                        : undefined
                }
                initialVersionNumber={workflow.version_number ?? null}
                initialVersionStatus={workflow.version_status ?? null}
                user={stableUser}
            />
        ) : null;
    }
}
