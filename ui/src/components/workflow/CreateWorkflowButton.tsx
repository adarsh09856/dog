'use client';

import { Bot, ChevronDown, LayoutTemplate, PlusIcon, Sparkles } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { toast } from 'sonner';

import { createWorkflowApiV1WorkflowCreateDefinitionPost } from '@/client/sdk.gen';
import { Badge } from '@/components/ui/badge';
import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { TemplateSelectorModal } from '@/components/workflow/TemplateSelectorModal';
import { useAuth } from '@/lib/auth';
import logger from '@/lib/logger';
import { getRandomId } from '@/lib/utils';

const BLANK_WORKFLOW_DEFINITION = {
    nodes: [
        {
            id: "1",
            type: "startCall",
            position: { x: 175, y: 60 },
            data: {
                prompt: "# Goal\nYou are a helpful agent who is handing a conversation over voice with a human. This is a voice conversation, so transcripts can be error prone.\n\n## Rules\n- Language: UK English but does not have to be correct english\n- Keep responses short and 2-3 sentences max\n- If you have to repeat something that you said in your previous two turns, then rephrase a bit while keeping the same meaning. Never repeat the exact same words as in your previous 2 responses.\n\n## Speech Handling\n- There could be multiple transcription errors. \n- Accept variations: yes/yeah/yep/aye, no/nah/nope\n- If user says \"sorry?\" or \"pardon me\" or \"can you repeat\"  or \"what?\", they might not have heard you- so just repeat what you just said.\n\n### Flow\nStart by saying \"Hi\". Be polite and courteous. ",
                name: "start call",
                allow_interrupt: false,
                invalid: false,
                validationMessage: null,
                add_global_prompt: false,
                delayed_start: false,
                is_start: true,
                selected_through_edge: false,
                hovered_through_edge: false,
                extraction_enabled: false,
                selected: false,
                dragging: false,
            },
        },
    ],
    edges: [],
    viewport: { x: 808, y: 269, zoom: 0.75 },
};

export function CreateWorkflowButton() {
    const router = useRouter();
    const { user, getAccessToken } = useAuth();
    const [isCreating, setIsCreating] = useState(false);
    const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);

    const handleAgentBuilder = () => {
        router.push('/workflow/create');
    };

    const handleBlankCanvas = async () => {
        if (isCreating || !user) return;
        setIsCreating(true);

        try {
            const accessToken = await getAccessToken();
            const name = `Agent-${getRandomId()}`;
            const response = await createWorkflowApiV1WorkflowCreateDefinitionPost({
                body: {
                    name,
                    workflow_definition: BLANK_WORKFLOW_DEFINITION as unknown as { [key: string]: unknown },
                },
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                },
            });

            if (response.data?.id) {
                router.push(`/workflow/${response.data.id}`);
            }
        } catch (err) {
            logger.error(`Error creating blank workflow: ${err}`);
            toast.error('Failed to create workflow');
        } finally {
            setIsCreating(false);
        }
    };

    return (
        <>
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button disabled={isCreating} className="gap-1.5 shadow-sm">
                        <PlusIcon className="w-4 h-4" />
                        {isCreating ? 'Creating...' : 'Create Agent'}
                        <ChevronDown className="w-3.5 h-3.5 opacity-70" />
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-64 p-1.5">
                    <DropdownMenuItem
                        onClick={() => setIsTemplateModalOpen(true)}
                        className="cursor-pointer py-2.5 px-3 rounded-md"
                    >
                        <div className="h-8 w-8 rounded-lg bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 flex items-center justify-center mr-3 shrink-0">
                            <Sparkles className="w-4 h-4" />
                        </div>
                        <div className="flex-1">
                            <div className="flex items-center gap-1.5 font-medium text-sm">
                                <span>Browse Templates</span>
                                <Badge variant="secondary" className="text-[10px] px-1 py-0 bg-primary/10 text-primary border-primary/20">
                                    Recommended
                                </Badge>
                            </div>
                            <div className="text-xs text-muted-foreground mt-0.5">
                                Receptionist, booking, support & more
                            </div>
                        </div>
                    </DropdownMenuItem>

                    <DropdownMenuItem
                        onClick={handleAgentBuilder}
                        className="cursor-pointer py-2 px-3 rounded-md"
                    >
                        <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center mr-3 shrink-0 text-muted-foreground">
                            <Bot className="w-4 h-4" />
                        </div>
                        <div>
                            <div className="font-medium text-sm">Agent Gallery & Builder</div>
                            <div className="text-xs text-muted-foreground">View full template gallery</div>
                        </div>
                    </DropdownMenuItem>

                    <DropdownMenuSeparator className="my-1" />

                    <DropdownMenuItem
                        onClick={handleBlankCanvas}
                        disabled={isCreating}
                        className="cursor-pointer py-2 px-3 rounded-md"
                    >
                        <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center mr-3 shrink-0 text-muted-foreground">
                            <LayoutTemplate className="w-4 h-4" />
                        </div>
                        <div>
                            <div className="font-medium text-sm">Blank Canvas</div>
                            <div className="text-xs text-muted-foreground">Start from scratch</div>
                        </div>
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>

            <TemplateSelectorModal
                open={isTemplateModalOpen}
                onOpenChange={setIsTemplateModalOpen}
            />
        </>
    );
}
