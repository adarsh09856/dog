'use client';

import {
    ArrowRight,
    Bot,
    Calendar,
    Check,
    CreditCard,
    Headphones,
    HeartPulse,
    Home,
    LayoutTemplate,
    MessageSquare,
    PhoneCall,
    Search,
    Sparkles,
    TrendingUp,
    UtensilsCrossed,
    Volume2,
    Wand2,
    AlertTriangle,
} from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

import { createWorkflowApiV1WorkflowCreateDefinitionPost } from '@/client/sdk.gen';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import {
    AGENT_TEMPLATES,
    AgentTemplate,
    generateTemplateWorkflowDefinition,
    TEMPLATE_CATEGORIES,
} from '@/constants/agentTemplates';
import { useAuth } from '@/lib/auth';
import { catalogApi, type AvailableCatalogResponse } from '@/lib/kodewavesApi';
import logger from '@/lib/logger';
import { getRandomId } from '@/lib/utils';

function getTemplateIcon(iconName: string) {
    switch (iconName) {
        case 'PhoneCall':
            return PhoneCall;
        case 'Calendar':
            return Calendar;
        case 'TrendingUp':
            return TrendingUp;
        case 'Headphones':
            return Headphones;
        case 'Home':
            return Home;
        case 'HeartPulse':
            return HeartPulse;
        case 'CreditCard':
            return CreditCard;
        case 'UtensilsCrossed':
            return UtensilsCrossed;
        case 'MessageSquare':
            return MessageSquare;
        case 'Bot':
            return Bot;
        case 'Sparkles':
            return Sparkles;
        default:
            return Bot;
    }
}

const COLOR_MAP: Record<string, { bg: string; text: string; border: string; iconBg: string }> = {
    emerald: {
        bg: 'bg-emerald-50 dark:bg-emerald-950/30',
        text: 'text-emerald-700 dark:text-emerald-300',
        border: 'border-emerald-200 dark:border-emerald-800',
        iconBg: 'bg-emerald-500 text-white',
    },
    blue: {
        bg: 'bg-blue-50 dark:bg-blue-950/30',
        text: 'text-blue-700 dark:text-blue-300',
        border: 'border-blue-200 dark:border-blue-800',
        iconBg: 'bg-blue-500 text-white',
    },
    violet: {
        bg: 'bg-violet-50 dark:bg-violet-950/30',
        text: 'text-violet-700 dark:text-violet-300',
        border: 'border-violet-200 dark:border-violet-800',
        iconBg: 'bg-violet-500 text-white',
    },
    rose: {
        bg: 'bg-rose-50 dark:bg-rose-950/30',
        text: 'text-rose-700 dark:text-rose-300',
        border: 'border-rose-200 dark:border-rose-800',
        iconBg: 'bg-rose-500 text-white',
    },
    amber: {
        bg: 'bg-amber-50 dark:bg-amber-950/30',
        text: 'text-amber-700 dark:text-amber-300',
        border: 'border-amber-200 dark:border-amber-800',
        iconBg: 'bg-amber-500 text-white',
    },
    cyan: {
        bg: 'bg-cyan-50 dark:bg-cyan-950/30',
        text: 'text-cyan-700 dark:text-cyan-300',
        border: 'border-cyan-200 dark:border-cyan-800',
        iconBg: 'bg-cyan-500 text-white',
    },
    slate: {
        bg: 'bg-slate-50 dark:bg-slate-900/30',
        text: 'text-slate-700 dark:text-slate-300',
        border: 'border-slate-200 dark:border-slate-800',
        iconBg: 'bg-slate-600 text-white',
    },
    orange: {
        bg: 'bg-orange-50 dark:bg-orange-950/30',
        text: 'text-orange-700 dark:text-orange-300',
        border: 'border-orange-200 dark:border-orange-800',
        iconBg: 'bg-orange-500 text-white',
    },
    teal: {
        bg: 'bg-teal-50 dark:bg-teal-950/30',
        text: 'text-teal-700 dark:text-teal-300',
        border: 'border-teal-200 dark:border-teal-800',
        iconBg: 'bg-teal-500 text-white',
    },
    indigo: {
        bg: 'bg-indigo-50 dark:bg-indigo-950/30',
        text: 'text-indigo-700 dark:text-indigo-300',
        border: 'border-indigo-200 dark:border-indigo-800',
        iconBg: 'bg-indigo-500 text-white',
    },
};

const BLANK_WORKFLOW_DEFINITION = {
    nodes: [
        {
            id: '1',
            type: 'startCall',
            position: { x: 175, y: 60 },
            data: {
                prompt: '# Goal\nYou are a helpful agent who is handing a conversation over voice with a human. This is a voice conversation, so transcripts can be error prone.\n\n## Rules\n- Language: English\n- Keep responses short and 2-3 sentences max\n\n### Flow\nStart by greeting the caller politely.',
                name: 'start call',
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

export default function CreateWorkflowPage() {
    const router = useRouter();
    const { user, getAccessToken } = useAuth();
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState<string>('all');
    const [previewTemplate, setPreviewTemplate] = useState<AgentTemplate | null>(null);
    const [customAgentName, setCustomAgentName] = useState('');
    const [customCompanyName, setCustomCompanyName] = useState('');
    const [isCreating, setIsCreating] = useState(false);

    const [customBuilderName, setCustomBuilderName] = useState('');
    const [customBuilderDescription, setCustomBuilderDescription] = useState('');
    const [customBuilderPrompt, setCustomBuilderPrompt] = useState('');

    const [catalog, setCatalog] = useState<AvailableCatalogResponse | null>(null);
    const [catalogLoading, setCatalogLoading] = useState(true);

    useEffect(() => {
        catalogApi.getAvailableCatalog()
            .then((data) => setCatalog(data))
            .catch((err) => console.warn('[CreateWorkflow] Failed to fetch catalog:', err))
            .finally(() => setCatalogLoading(false));
    }, []);

    const isCatalogEmpty = useMemo(() => {
        if (catalogLoading || !catalog) return false;
        const total = (catalog.cloud_llm_models?.length ?? 0) +
            (catalog.local_llm_models?.length ?? 0) +
            (catalog.s2s_models?.length ?? 0);
        return total === 0;
    }, [catalog, catalogLoading]);

    const filteredTemplates = useMemo(() => {
        return AGENT_TEMPLATES.filter((tpl) => {
            const matchesCategory =
                selectedCategory === 'all' || tpl.category === selectedCategory;
            const query = searchQuery.toLowerCase().trim();
            const matchesSearch =
                !query ||
                tpl.name.toLowerCase().includes(query) ||
                tpl.description.toLowerCase().includes(query) ||
                tpl.features.some((f) => f.toLowerCase().includes(query));
            return matchesCategory && matchesSearch;
        });
    }, [searchQuery, selectedCategory]);

    const handleOpenPreview = (tpl: AgentTemplate) => {
        setPreviewTemplate(tpl);
        setCustomAgentName(tpl.name);
        setCustomCompanyName('');
    };

    const handleDeployTemplate = async () => {
        if (!previewTemplate || !user || isCreating) return;

        setIsCreating(true);
        try {
            const accessToken = await getAccessToken();
            const finalAgentName = customAgentName.trim() || previewTemplate.name;
            const finalCompanyName = customCompanyName.trim() || 'our company';

            const definition = generateTemplateWorkflowDefinition(previewTemplate, {
                agentName: finalAgentName,
                companyName: finalCompanyName,
            });

            const response = await createWorkflowApiV1WorkflowCreateDefinitionPost({
                body: {
                    name: finalAgentName,
                    workflow_definition: definition as unknown as { [key: string]: unknown },
                },
                headers: {
                    Authorization: `Bearer ${accessToken}`,
                },
            });

            if (response.data?.id) {
                toast.success(`Agent "${finalAgentName}" created successfully!`);
                setPreviewTemplate(null);
                router.push(`/workflow/${response.data.id}?onboarding=web_call`);
            } else {
                toast.error('Failed to create agent.');
            }
        } catch (err) {
            logger.error(`Error deploying template: ${err}`);
            toast.error('Failed to create agent from template.');
        } finally {
            setIsCreating(false);
        }
    };

    const handleCreateBlank = async () => {
        if (!user || isCreating) return;
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
                    Authorization: `Bearer ${accessToken}`,
                },
            });

            if (response.data?.id) {
                toast.success('Blank canvas agent created!');
                router.push(`/workflow/${response.data.id}`);
            }
        } catch (err) {
            logger.error(`Error creating blank workflow: ${err}`);
            toast.error('Failed to create workflow');
        } finally {
            setIsCreating(false);
        }
    };

    const handleCreateCustom = async () => {
        if (!customBuilderName.trim() || isCreating) {
            toast.error('Please enter an agent name.');
            return;
        }

        setIsCreating(true);
        try {
            const accessToken = await getAccessToken();
            const promptText =
                customBuilderPrompt.trim() ||
                `# Goal\nYou are a voice AI agent handling: ${customBuilderDescription || customBuilderName}.\n\n## Rules\n- Speak naturally\n- Keep turns short (1-3 sentences max).`;

            const definition = {
                nodes: [
                    {
                        id: '1',
                        type: 'startCall',
                        position: { x: 175, y: 60 },
                        data: {
                            name: 'start call',
                            prompt: promptText,
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

            const response = await createWorkflowApiV1WorkflowCreateDefinitionPost({
                body: {
                    name: customBuilderName.trim(),
                    workflow_definition: definition as unknown as { [key: string]: unknown },
                },
                headers: {
                    Authorization: `Bearer ${accessToken}`,
                },
            });

            if (response.data?.id) {
                toast.success(`Agent "${customBuilderName}" created!`);
                router.push(`/workflow/${response.data.id}?onboarding=web_call`);
            }
        } catch (err) {
            logger.error(`Error creating custom workflow: ${err}`);
            toast.error('Failed to create custom agent.');
        } finally {
            setIsCreating(false);
        }
    };

    return (
        <div className="min-h-screen bg-background">
            <div className="container mx-auto px-4 py-8 max-w-6xl">
                {/* Hero Header */}
                <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-50/50 via-purple-50/30 to-pink-50/50 dark:from-indigo-950/20 dark:via-purple-900/10 dark:to-pink-950/20 border p-6 md:p-8 mb-8">
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                        <div className="space-y-2">
                            <div className="flex items-center gap-2">
                                <Badge variant="secondary" className="gap-1 px-2.5 py-0.5 bg-primary/10 text-primary border-primary/20">
                                    <Sparkles className="w-3.5 h-3.5" />
                                    Agent Templates Gallery
                                </Badge>
                                <span className="text-xs text-muted-foreground">Kodewaves Platform</span>
                            </div>
                            <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight">
                                Create Your Voice Agent
                            </h1>
                            <p className="text-muted-foreground max-w-2xl text-sm md:text-base">
                                Choose from battle-tested, pre-built agent templates configured with natural conversational flow, or build your own custom voice agent from scratch.
                            </p>
                        </div>
                        <div className="flex flex-wrap gap-2 shrink-0">
                            <Button
                                variant="outline"
                                onClick={handleCreateBlank}
                                disabled={isCreating}
                                className="shadow-sm"
                            >
                                <LayoutTemplate className="w-4 h-4 mr-2" />
                                Start Blank Canvas
                            </Button>
                        </div>
                    </div>
                </div>

                {/* Empty Catalog Warning */}
                {isCatalogEmpty && (
                    <div className="mb-8 p-4 rounded-xl border border-red-500/30 bg-red-500/10 text-red-900 dark:text-red-200 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                        <div className="flex items-start gap-3">
                            <AlertTriangle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
                            <div>
                                <p className="font-semibold text-sm">No Active AI Models Available in Catalog</p>
                                <p className="text-xs text-red-700 dark:text-red-300 mt-0.5">
                                    Your platform currently has no verified AI models configured. Agents require at least one active LLM or S2S engine to function. Configure master provider keys in Admin or enter your BYOK credentials.
                                </p>
                            </div>
                        </div>
                        <div className="flex gap-2 shrink-0">
                            <Button size="sm" variant="outline" asChild className="border-red-500/30 hover:bg-red-500/20">
                                <Link href="/model-configurations">Configure BYOK</Link>
                            </Button>
                            <Button size="sm" asChild className="bg-red-600 hover:bg-red-700 text-white">
                                <Link href="/admin/models">Admin Settings</Link>
                            </Button>
                        </div>
                    </div>
                )}

                {/* Main Tabs */}
                <Tabs defaultValue="templates" className="space-y-6">
                    <TabsList className="grid w-full max-w-md grid-cols-2">
                        <TabsTrigger value="templates" className="gap-2">
                            <Sparkles className="w-4 h-4" />
                            Browse Templates ({AGENT_TEMPLATES.length})
                        </TabsTrigger>
                        <TabsTrigger value="custom" className="gap-2">
                            <Wand2 className="w-4 h-4" />
                            Custom Builder
                        </TabsTrigger>
                    </TabsList>

                    {/* Templates Tab */}
                    <TabsContent value="templates" className="space-y-6">
                        {/* Search & Category Pills */}
                        <div className="flex flex-col md:flex-row gap-4 justify-between items-stretch md:items-center">
                            <div className="relative flex-1 max-w-md">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                <Input
                                    placeholder="Search by role, feature, or keyword..."
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    className="pl-9"
                                />
                            </div>

                            <div className="flex gap-1.5 overflow-x-auto pb-1">
                                {TEMPLATE_CATEGORIES.map((cat) => (
                                    <Button
                                        key={cat.value}
                                        variant={selectedCategory === cat.value ? 'default' : 'outline'}
                                        size="sm"
                                        onClick={() => setSelectedCategory(cat.value)}
                                        className="h-8 text-xs shrink-0"
                                    >
                                        {cat.label}
                                    </Button>
                                ))}
                            </div>
                        </div>

                        {/* Templates Grid */}
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {filteredTemplates.map((template) => {
                                const IconComponent = getTemplateIcon(template.icon);
                                const colorStyles = COLOR_MAP[template.color] || COLOR_MAP.slate;

                                return (
                                    <Card
                                        key={template.id}
                                        className="group relative flex flex-col justify-between hover:shadow-lg transition-all duration-200 border hover:border-primary/50 overflow-hidden"
                                    >
                                        <CardHeader className="pb-3">
                                            <div className="flex items-start justify-between gap-2 mb-2">
                                                <div
                                                    className={`h-11 w-11 rounded-xl flex items-center justify-center shrink-0 shadow-sm transition-transform group-hover:scale-105 ${colorStyles.iconBg}`}
                                                >
                                                    <IconComponent className="h-5 w-5" />
                                                </div>
                                                <Badge
                                                    variant="secondary"
                                                    className={`text-[10px] uppercase font-semibold tracking-wider ${colorStyles.bg} ${colorStyles.text}`}
                                                >
                                                    {template.badge}
                                                </Badge>
                                            </div>
                                            <CardTitle className="text-base group-hover:text-primary transition-colors">
                                                {template.name}
                                            </CardTitle>
                                            <CardDescription className="text-xs line-clamp-2 mt-1">
                                                {template.description}
                                            </CardDescription>
                                        </CardHeader>

                                        <CardContent className="space-y-4 pt-0">
                                            {/* Feature tags */}
                                            <div className="flex flex-wrap gap-1">
                                                {template.features.slice(0, 3).map((feat) => (
                                                    <span
                                                        key={feat}
                                                        className="inline-flex items-center text-[10px] bg-muted/80 px-2 py-0.5 rounded text-muted-foreground font-medium"
                                                    >
                                                        <Check className="w-2.5 h-2.5 mr-1 text-emerald-500" />
                                                        {feat}
                                                    </span>
                                                ))}
                                                {template.features.length > 3 && (
                                                    <span className="text-[10px] text-muted-foreground self-center px-1">
                                                        +{template.features.length - 3} more
                                                    </span>
                                                )}
                                            </div>

                                            {/* Action buttons */}
                                            <div className="pt-2 border-t flex items-center gap-2">
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    onClick={() => handleOpenPreview(template)}
                                                    className="flex-1 text-xs"
                                                >
                                                    Preview Details
                                                </Button>
                                                <Button
                                                    size="sm"
                                                    onClick={() => handleOpenPreview(template)}
                                                    className="flex-1 text-xs gap-1 bg-primary hover:bg-primary/90"
                                                >
                                                    <span>Use Template</span>
                                                    <ArrowRight className="w-3.5 h-3.5" />
                                                </Button>
                                            </div>
                                        </CardContent>
                                    </Card>
                                );
                            })}
                        </div>

                        {filteredTemplates.length === 0 && (
                            <div className="text-center py-12 border rounded-xl bg-muted/10">
                                <Bot className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
                                <h3 className="font-semibold text-lg">No templates found</h3>
                                <p className="text-sm text-muted-foreground mt-1">
                                    No templates matched your search query. Try clearing your filters.
                                </p>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => {
                                        setSearchQuery('');
                                        setSelectedCategory('all');
                                    }}
                                    className="mt-4"
                                >
                                    Reset Filters
                                </Button>
                            </div>
                        )}
                    </TabsContent>

                    {/* Custom Prompt Builder Tab */}
                    <TabsContent value="custom">
                        <Card className="max-w-2xl mx-auto">
                            <CardHeader>
                                <CardTitle className="text-xl">Custom Voice Agent Builder</CardTitle>
                                <CardDescription>
                                    Define your own agent goals, personality, and prompt from scratch.
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-5">
                                <div className="space-y-2">
                                    <Label htmlFor="custom-builder-name">Agent Name</Label>
                                    <Input
                                        id="custom-builder-name"
                                        placeholder="e.g. Acme Tech Support Specialist"
                                        value={customBuilderName}
                                        onChange={(e) => setCustomBuilderName(e.target.value)}
                                    />
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="custom-builder-desc">Primary Purpose / Role</Label>
                                    <Input
                                        id="custom-builder-desc"
                                        placeholder="e.g. Help users troubleshoot hardware and schedule technician visits"
                                        value={customBuilderDescription}
                                        onChange={(e) => setCustomBuilderDescription(e.target.value)}
                                    />
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="custom-builder-prompt">
                                        System Prompt & Instructions (Optional)
                                    </Label>
                                    <Textarea
                                        id="custom-builder-prompt"
                                        placeholder="Define the agent's goal, rules, and conversation flow. Leave blank to generate standard polite voice prompt."
                                        rows={6}
                                        value={customBuilderPrompt}
                                        onChange={(e) => setCustomBuilderPrompt(e.target.value)}
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        You can refine the prompt and add tools or actions inside the canvas editor anytime.
                                    </p>
                                </div>

                                <div className="pt-2">
                                    <Button
                                        onClick={handleCreateCustom}
                                        disabled={isCreating || !customBuilderName.trim()}
                                        className="w-full"
                                    >
                                        {isCreating ? 'Creating Agent...' : 'Create Voice Agent'}
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    </TabsContent>
                </Tabs>

                {/* Template Preview and Customization Modal */}
                {previewTemplate && (
                    <Dialog open={!!previewTemplate} onOpenChange={(open) => !open && setPreviewTemplate(null)}>
                        <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col p-0 overflow-hidden">
                            <DialogHeader className="px-6 pt-6 pb-4 border-b">
                                <div className="flex items-center gap-3">
                                    <div
                                        className={`h-11 w-11 rounded-xl flex items-center justify-center shrink-0 ${COLOR_MAP[previewTemplate.color]?.iconBg || 'bg-primary text-white'}`}
                                    >
                                        {(() => {
                                            const IconComp = getTemplateIcon(previewTemplate.icon);
                                            return <IconComp className="h-6 w-6" />;
                                        })()}
                                    </div>
                                    <div>
                                        <div className="flex items-center gap-2">
                                            <DialogTitle className="text-lg font-bold">
                                                {previewTemplate.name}
                                            </DialogTitle>
                                            <Badge variant="outline" className="text-xs">
                                                {previewTemplate.badge}
                                            </Badge>
                                        </div>
                                        <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                                            {previewTemplate.description}
                                        </DialogDescription>
                                    </div>
                                </div>
                            </DialogHeader>

                            <div className="flex-1 overflow-y-auto p-6 space-y-5">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="space-y-1.5">
                                        <Label htmlFor="preview-agent-name" className="text-xs font-semibold">
                                            Agent Name
                                        </Label>
                                        <Input
                                            id="preview-agent-name"
                                            value={customAgentName}
                                            onChange={(e) => setCustomAgentName(e.target.value)}
                                            placeholder={previewTemplate.name}
                                            className="h-9"
                                        />
                                    </div>

                                    <div className="space-y-1.5">
                                        <Label htmlFor="preview-company-name" className="text-xs font-semibold">
                                            Company Name (Optional)
                                        </Label>
                                        <Input
                                            id="preview-company-name"
                                            value={customCompanyName}
                                            onChange={(e) => setCustomCompanyName(e.target.value)}
                                            placeholder="e.g. Acme Corp"
                                            className="h-9"
                                        />
                                    </div>
                                </div>

                                <div className="bg-muted/40 rounded-lg p-3 border space-y-2">
                                    <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                                        <Volume2 className="h-3.5 w-3.5 text-primary" />
                                        Voice Tone & Persona
                                    </div>
                                    <p className="text-xs text-muted-foreground">
                                        <span className="font-semibold text-foreground">Suggested Tone:</span>{' '}
                                        {previewTemplate.suggestedVoiceTone}
                                    </p>
                                    <p className="text-xs text-muted-foreground">
                                        <span className="font-semibold text-foreground">Persona:</span>{' '}
                                        {previewTemplate.suggestedPersonality}
                                    </p>
                                </div>

                                <div className="space-y-2">
                                    <Label className="text-xs font-semibold flex items-center gap-1.5">
                                        <MessageSquare className="h-3.5 w-3.5 text-primary" />
                                        First Spoken Greeting
                                    </Label>
                                    <div className="bg-muted/30 p-3 rounded-lg border text-xs text-foreground italic">
                                        &ldquo;
                                        {previewTemplate.suggestedFirstMessage
                                            .replace(/\{\{company_name\}\}/g, customCompanyName.trim() || 'our company')
                                            .replace(/\{\{agent_name\}\}/g, customAgentName.trim() || previewTemplate.name)}
                                        &rdquo;
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <Label className="text-xs font-semibold flex items-center gap-1.5">
                                        <Sparkles className="h-3.5 w-3.5 text-primary" />
                                        System Prompt Preview
                                    </Label>
                                    <div className="bg-muted/20 p-3 rounded-lg border text-xs font-mono text-muted-foreground max-h-52 overflow-y-auto whitespace-pre-wrap">
                                        {previewTemplate.suggestedPrompt
                                            .replace(/\{\{company_name\}\}/g, customCompanyName.trim() || 'our company')
                                            .replace(/\{\{agent_name\}\}/g, customAgentName.trim() || previewTemplate.name)}
                                    </div>
                                </div>
                            </div>

                            <DialogFooter className="px-6 py-4 border-t bg-muted/20 flex items-center justify-between">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setPreviewTemplate(null)}
                                    disabled={isCreating}
                                >
                                    Cancel
                                </Button>
                                <Button
                                    onClick={handleDeployTemplate}
                                    disabled={isCreating || !customAgentName.trim()}
                                    className="bg-primary hover:bg-primary/90"
                                >
                                    {isCreating ? (
                                        <>
                                            <div className="h-4 w-4 mr-2 animate-spin rounded-full border-2 border-current border-t-transparent" />
                                            Creating Agent...
                                        </>
                                    ) : (
                                        <>
                                            <Sparkles className="h-4 w-4 mr-2" />
                                            Create Voice Agent
                                        </>
                                    )}
                                </Button>
                            </DialogFooter>
                        </DialogContent>
                    </Dialog>
                )}
            </div>
        </div>
    );
}
