"use client";

import { Loader2, MessageSquareText, Mic, Phone, RefreshCw, X } from "lucide-react";
import posthog from "posthog-js";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { createWorkflowRunApiV1WorkflowWorkflowIdRunsPost } from "@/client/sdk.gen";
import chrome from "@/components/layout/WorkspaceChrome.module.css";
import { OnboardingTooltip } from "@/components/onboarding/OnboardingTooltip";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PostHogEvent } from "@/constants/posthog-events";
import { WORKFLOW_RUN_MODES } from "@/constants/workflowRunModes";
import { useOnboarding } from "@/context/OnboardingContext";
import { useAuth } from "@/lib/auth";
import { cn, getRandomId } from "@/lib/utils";

import { EmbeddedVoiceTester } from "./workflow-tester/EmbeddedVoiceTester";
import { ManualTextChatPanel } from "./workflow-tester/ManualTextChatPanel";
import { DisabledNotice, EmptyState } from "./workflow-tester/shared";
import type { WorkflowRuntimeNodeTransition } from "./workflow-tester/types";
import { extractSdkErrorMessage, getErrorMessage } from "./workflow-tester/utils";
import testerStyle from "./WorkflowTesterWorkspace.module.css";

interface WorkflowTesterPanelProps {
    workflowId: number;
    initialContextVariables?: Record<string, string>;
    disabled: boolean;
    disabledReason: string | null;
    showWebCallOnboarding?: boolean;
    isVisible?: boolean;
    className?: string;
    onClose?: () => void;
    onRuntimeNodeTransition?: (transition: WorkflowRuntimeNodeTransition) => void;
}

export function WorkflowTesterPanel({
    workflowId,
    initialContextVariables,
    disabled,
    disabledReason,
    showWebCallOnboarding = false,
    isVisible = true,
    className,
    onClose,
    onRuntimeNodeTransition,
}: WorkflowTesterPanelProps) {
    const auth = useAuth();
    const { markActionCompleted } = useOnboarding();
    const { isAuthenticated, loading: authLoading, getAccessToken } = auth;
    const [accessToken, setAccessToken] = useState<string | null>(null);
    const [activeMode, setActiveMode] = useState<"audio" | "text">("audio");
    const [chatSessionKey, setChatSessionKey] = useState(0);
    const [chatActive, setChatActive] = useState(false);
    const [voiceRunId, setVoiceRunId] = useState<number | null>(null);
    const [creatingVoiceRun, setCreatingVoiceRun] = useState(false);
    const [tokenReady, setTokenReady] = useState(false);
    const runTestButtonRef = useRef<HTMLButtonElement>(null);

    useEffect(() => {
        let ignore = false;

        const hydrateAccessToken = async () => {
            if (!isAuthenticated || authLoading) return;
            try {
                const token = await getAccessToken();
                if (!ignore) {
                    setAccessToken(token);
                }
            } catch (error) {
                if (!ignore) {
                    toast.error(getErrorMessage(error));
                }
            } finally {
                if (!ignore) {
                    setTokenReady(true);
                }
            }
        };

        if (authLoading) {
            return;
        }

        if (!isAuthenticated) {
            setTokenReady(true);
            return;
        }

        hydrateAccessToken();

        return () => {
            ignore = true;
        };
    }, [authLoading, getAccessToken, isAuthenticated]);

    const createVoiceRun = useCallback(async () => {
        if (!accessToken || disabled) return;
        setCreatingVoiceRun(true);
        try {
            const response = await createWorkflowRunApiV1WorkflowWorkflowIdRunsPost({
                path: { workflow_id: workflowId },
                body: {
                    mode: WORKFLOW_RUN_MODES.SMALL_WEBRTC,
                    name: `WR-${getRandomId()}`,
                },
            });

            if (response.error || !response.data?.id) {
                throw new Error(extractSdkErrorMessage(response.error, "Failed to create browser test run"));
            }

            markActionCompleted("web_call_started");
            posthog.capture(PostHogEvent.WEB_CALL_INITIATED, {
                workflow_id: workflowId,
                workflow_run_id: response.data.id,
                source: "workflow_editor",
            });
            setVoiceRunId(response.data.id);
            setActiveMode("audio");
        } catch (error) {
            toast.error(getErrorMessage(error));
        } finally {
            setCreatingVoiceRun(false);
        }
    }, [accessToken, disabled, markActionCompleted, workflowId]);

    const authUnavailableReason = tokenReady && !accessToken
        ? "Authentication is required before testing can start."
        : null;
    const effectiveDisabledReason = disabledReason ?? authUnavailableReason;
    const testerBlocked = disabled || authUnavailableReason !== null;
    const runTestTooltipEnabled =
        showWebCallOnboarding &&
        isVisible &&
        activeMode === "audio" &&
        !voiceRunId &&
        tokenReady &&
        !!accessToken &&
        !testerBlocked;

    const handleModeChange = (value: string) => {
        const mode = value as "audio" | "text";
        setActiveMode(mode);
        if (mode !== "audio") {
            // Leaving this tab unmounts EmbeddedVoiceTester, whose cleanup closes
            // the socket and peer connection — the call is over at that point and
            // the backend completes the run. A run may only be called once, so
            // release the id here; coming back mints a fresh one rather than
            // re-offering a finished run.
            setVoiceRunId(null);
        }
    };

    return (
        <div className={cn(chrome.testerPanel, testerStyle.panel, "flex h-full min-h-0 flex-col text-card-foreground", className)}>
            <div className={testerStyle.heading}>
                <span className={testerStyle.eyebrow}>Build / Agent playground</span>
                <h2 className={testerStyle.title}>Test your agent</h2>
                <p className={testerStyle.description}>Check the voice and chat experience before you publish.</p>
            </div>
            <Tabs
                value={activeMode}
                onValueChange={handleModeChange}
                className="min-h-0 flex-1 gap-0"
            >
                <div className={testerStyle.tabsHeader}>
                    <p className="mb-2 font-mono text-[9px] font-medium uppercase tracking-[.16em] text-muted-foreground">Choose a test mode</p>
                    <div className="flex items-center gap-3">
                        <TabsList className={cn(testerStyle.tabList, "grid h-10 flex-1 grid-cols-2 rounded-xl p-1 shadow-inner shadow-foreground/[0.03]")}>
                            <TabsTrigger value="audio" className="rounded-lg text-sm font-medium data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm">
                                <Mic className="h-4 w-4" />
                                Test Audio
                            </TabsTrigger>
                            <TabsTrigger value="text" className="rounded-lg text-sm font-medium data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm">
                                <MessageSquareText className="h-4 w-4" />
                                Test Chat
                            </TabsTrigger>
                        </TabsList>
                        {onClose ? (
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={onClose}
                                className="shrink-0 text-muted-foreground hover:text-foreground"
                                aria-label="Close tester panel"
                            >
                                <X className="h-4 w-4" />
                            </Button>
                        ) : null}
                    </div>
                </div>

                <TabsContent value="audio" className={cn(testerStyle.audioContent, "min-h-0 flex-1 px-4 py-4")}>
                    <div className="flex h-full min-h-0 flex-col gap-3">
                        {tokenReady && accessToken && !voiceRunId && !effectiveDisabledReason ? (
                            <div className={testerStyle.modeIntro}>
                                <div>
                                    <strong>Browser voice preview</strong>
                                    <p>Start a temporary call and speak naturally with this agent.</p>
                                </div>
                                <span className={testerStyle.modeTag}>AUDIO</span>
                            </div>
                        ) : null}
                        {!tokenReady ? (
                            <div className="space-y-4">
                                <Skeleton className="h-14 rounded-xl" />
                                <Skeleton className="h-80 rounded-xl" />
                            </div>
                        ) : !accessToken ? (
                            <DisabledNotice
                                reason={authUnavailableReason ?? "Authentication is required before browser tests can start."}
                            />
                        ) : voiceRunId ? (
                            <EmbeddedVoiceTester
                                workflowId={workflowId}
                                workflowRunId={voiceRunId}
                                initialContextVariables={initialContextVariables}
                                accessToken={accessToken}
                                onReset={() => setVoiceRunId(null)}
                                onNodeTransition={onRuntimeNodeTransition}
                            />
                        ) : (
                            <>
                                {effectiveDisabledReason ? <DisabledNotice reason={effectiveDisabledReason} /> : null}
                                <EmptyState
                                    icon={<Phone className="h-7 w-7" />}
                                    title="Call this agent in the browser"
                                    description="Test the agent over a voice call. Some telephony-only tools, like call transfer, are not yet supported here."
                                    action={
                                        <Button
                                            ref={runTestButtonRef}
                                            onClick={createVoiceRun}
                                            disabled={creatingVoiceRun || testerBlocked}
                                        >
                                            {creatingVoiceRun ? (
                                                <>
                                                    <Loader2 className="h-4 w-4 animate-spin" />
                                                    Starting test...
                                                </>
                                            ) : (
                                                <>
                                                    <Phone className="h-4 w-4" />
                                                    Run Test
                                                </>
                                            )}
                                        </Button>
                                    }
                                />
                            </>
                        )}
                    </div>
                </TabsContent>

                <TabsContent value="text" className={cn(testerStyle.textContent, "min-h-0 flex-1 px-4 py-3")}>
                    <div className="flex h-full min-h-0 flex-col gap-3">
                        <div className={cn(testerStyle.chatToolbar, "flex items-center justify-between")}>
                            <div>
                                <span className={testerStyle.chatToolbarLabel}>Manual chat</span>
                                <p className="mt-0.5 text-[10px] text-muted-foreground">Send messages to check the agent’s text responses.</p>
                            </div>
                            {chatActive ? (
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => setChatSessionKey((value) => value + 1)}
                                    disabled={testerBlocked}
                                    className={cn(testerStyle.resetButton, "h-8 px-2.5 text-xs text-muted-foreground hover:text-foreground")}
                                >
                                    <RefreshCw className="h-3.5 w-3.5" />
                                    Reset
                                </Button>
                            ) : null}
                        </div>

                        <ManualTextChatPanel
                                key={chatSessionKey}
                                workflowId={workflowId}
                                ready={tokenReady && !!accessToken}
                                initialContextVariables={initialContextVariables}
                                disabled={testerBlocked}
                                disabledReason={effectiveDisabledReason}
                                onActiveChange={setChatActive}
                                onNodeTransition={onRuntimeNodeTransition}
                        />
                    </div>
                </TabsContent>
            </Tabs>

            <OnboardingTooltip
                tooltipKey="web_call"
                targetRef={runTestButtonRef}
                title="Try Your First Web Call"
                message="Start a browser call here to hear the agent, inspect the transcript, and validate the workflow before you customize it further."
                showNext={false}
                enabled={runTestTooltipEnabled}
            />
        </div>
    );
}
