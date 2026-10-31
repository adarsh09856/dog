'use client';

import {
    Bot,
    Calendar,
    Check,
    CreditCard,
    Headphones,
    HeartPulse,
    Home,
    MessageSquare,
    PhoneCall,
    Search,
    Sparkles,
    TrendingUp,
    UtensilsCrossed,
    Volume2,
    Wand2,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';
import { toast } from 'sonner';

import { createWorkflowApiV1WorkflowCreateDefinitionPost } from '@/client/sdk.gen';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
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
import {
    AGENT_TEMPLATES,
    AgentTemplate,
    generateTemplateWorkflowDefinition,
    TEMPLATE_CATEGORIES,
} from '@/constants/agentTemplates';
import { INDIAN_TEMPLATE_LANGUAGES } from '@/constants/languages';
import { detailFromError } from '@/lib/apiError';
import { useAuth } from '@/lib/auth';
import logger from '@/lib/logger';
import { configuredTemplateLanguage } from '@/lib/templateLanguage';

interface TemplateSelectorModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSuccess?: (workflowId: string) => void;
}

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
        bg: 'bg-emerald-50 dark:bg-emerald-950/30',
        text: 'text-emerald-700 dark:text-emerald-300',
        border: 'border-emerald-200 dark:border-emerald-800',
        iconBg: 'bg-emerald-500 text-white',
    },
    violet: {
        bg: 'bg-amber-50 dark:bg-amber-950/30',
        text: 'text-amber-800 dark:text-amber-300',
        border: 'border-amber-200 dark:border-amber-800',
        iconBg: 'bg-amber-500 text-white',
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
        bg: 'bg-teal-50 dark:bg-teal-950/30',
        text: 'text-teal-700 dark:text-teal-300',
        border: 'border-teal-200 dark:border-teal-800',
        iconBg: 'bg-teal-600 text-white',
    },
    slate: {
        bg: 'bg-muted/50',
        text: 'text-muted-foreground',
        border: 'border-border',
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
        bg: 'bg-emerald-50 dark:bg-emerald-950/30',
        text: 'text-emerald-700 dark:text-emerald-300',
        border: 'border-emerald-200 dark:border-emerald-800',
        iconBg: 'bg-emerald-500 text-white',
    },
};

export function TemplateSelectorModal({
    open,
    onOpenChange,
    onSuccess,
}: TemplateSelectorModalProps) {
    const router = useRouter();
    const { user, getAccessToken } = useAuth();
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState<string>('all');
    const [selectedTemplate, setSelectedTemplate] = useState<AgentTemplate | null>(null);
    const [customAgentName, setCustomAgentName] = useState('');
    const [customCompanyName, setCustomCompanyName] = useState('');
    const [templateLanguage, setTemplateLanguage] = useState<string>('en');
    const templatePreview = useMemo(() => selectedTemplate
        ? generateTemplateWorkflowDefinition(selectedTemplate, {
            agentName: customAgentName, companyName: customCompanyName, language: templateLanguage,
        }) : null, [selectedTemplate, customAgentName, customCompanyName, templateLanguage]);
    const [isDeploying, setIsDeploying] = useState(false);

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

    const handleSelectTemplate = async (template: AgentTemplate) => {
        const language = await configuredTemplateLanguage().catch(() => null);
        if (language) setTemplateLanguage(language);
        setSelectedTemplate(template);
        setCustomAgentName(template.name);
        setCustomCompanyName('');
    };

    const handleClosePreview = () => {
        setSelectedTemplate(null);
    };

    const handleDeploy = async () => {
        if (!selectedTemplate || !user || isDeploying) return;

        setIsDeploying(true);
        try {
            const accessToken = await getAccessToken();
            const finalAgentName = customAgentName.trim() || selectedTemplate.name;
            const finalCompanyName = customCompanyName.trim() || 'our company';

            const workflowDefinition = generateTemplateWorkflowDefinition(selectedTemplate, {
                agentName: finalAgentName,
                companyName: finalCompanyName,
                language: templateLanguage,
            });

            const response = await createWorkflowApiV1WorkflowCreateDefinitionPost({
                body: {
                    name: finalAgentName,
                    workflow_definition: workflowDefinition as unknown as { [key: string]: unknown },
                },
                headers: {
                    Authorization: `Bearer ${accessToken}`,
                },
            });

            if (response.data?.id) {
                const newId = String(response.data.id);
                toast.success(`Agent "${finalAgentName}" created successfully!`);
                onOpenChange(false);
                if (onSuccess) {
                    onSuccess(newId);
                } else {
                    router.push(`/workflow/${newId}?onboarding=web_call`);
                }
            } else {
                toast.error(detailFromError(response.error, 'Failed to create agent. Please try again.'));
            }
        } catch (err) {
            logger.error(`Error deploying template: ${err}`);
            toast.error('Failed to create agent from template.');
        } finally {
            setIsDeploying(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-4xl max-h-[90vh] flex min-h-0 flex-col overflow-hidden p-0">
                <DialogHeader className="shrink-0 px-6 pt-6 pb-4 border-b">
                    <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-xl bg-primary text-primary-foreground flex items-center justify-center shadow-md">
                            <Wand2 className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 pr-7">
                            <DialogTitle className="text-xl font-bold">
                                Choose an Agent Template
                            </DialogTitle>
                            <DialogDescription className="text-sm leading-relaxed text-foreground/75">
                                Select from pre-built, industry-tuned voice agents with prompts and speech logic ready to deploy.
                            </DialogDescription>
                        </div>
                    </div>

                    {/* Search and Filters */}
                    <div className="mt-4 flex flex-col sm:flex-row gap-3">
                        <div className="relative flex-1">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                            <Input
                                placeholder="Search templates by role, feature, or keyword..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="pl-9 h-9"
                            />
                        </div>
                        <div className="flex gap-1 overflow-x-auto pb-1 max-w-full">
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
                </DialogHeader>

                {/* Templates Grid / Preview Body */}
                <div className="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain p-6">
                    {selectedTemplate ? (
                        /* Selected Template Preview & Customize View */
                        <div className="space-y-6">
                            <div className="flex items-center justify-between pb-3 border-b">
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={handleClosePreview}
                                    className="text-xs"
                                >
                                    &larr; Back to all templates
                                </Button>
                                <Badge variant="outline" className="text-xs font-semibold">
                                    {selectedTemplate.badge}
                                </Badge>
                            </div>

                            <div className="grid min-w-0 grid-cols-1 gap-6 md:grid-cols-2">
                                {/* Left Column: Configuration */}
                                <div className="min-w-0 space-y-4">
                                    <div className="flex items-start gap-3">
                                        <div
                                            className={`h-12 w-12 rounded-xl flex items-center justify-center shrink-0 ${COLOR_MAP[selectedTemplate.color]?.iconBg || 'bg-primary text-white'}`}
                                        >
                                            {(() => {
                                                const IconComp = getTemplateIcon(selectedTemplate.icon);
                                                return <IconComp className="h-6 w-6" />;
                                            })()}
                                        </div>
                                        <div className="min-w-0">
                                            <h3 className="text-lg font-bold">
                                                {selectedTemplate.name}
                                            </h3>
                                            <p className="text-xs text-muted-foreground mt-0.5">
                                                {selectedTemplate.description}
                                            </p>
                                        </div>
                                    </div>

                                    <div className="space-y-3 pt-2">
                                        <div>
                                            <Label htmlFor="modal-template-language">Template language</Label>
                                            <select id="modal-template-language" value={templateLanguage}
                                                onChange={e => setTemplateLanguage(e.target.value)}
                                                className="mt-1 flex h-9 w-full rounded-md border bg-background px-3 text-sm">
                                                <option value="en">English</option>
                                                {INDIAN_TEMPLATE_LANGUAGES.map(({ code, name }) => (
                                                    <option key={code} value={code}>{name}</option>
                                                ))}
                                            </select>
                                            <p className="mt-1 text-xs text-muted-foreground">Choose the prompt language. The speech models and voice must support it in Models.</p>
                                        </div>
                                        <div>
                                            <Label htmlFor="custom-agent-name" className="text-xs font-semibold">
                                                Agent Name
                                            </Label>
                                            <Input
                                                id="custom-agent-name"
                                                value={customAgentName}
                                                onChange={(e) => setCustomAgentName(e.target.value)}
                                                placeholder="e.g. Front Desk Receptionist"
                                                className="mt-1 h-9"
                                            />
                                        </div>

                                        <div>
                                            <Label htmlFor="custom-company-name" className="text-xs font-semibold">
                                                Company / Business Name (Optional)
                                            </Label>
                                            <Input
                                                id="custom-company-name"
                                                value={customCompanyName}
                                                onChange={(e) => setCustomCompanyName(e.target.value)}
                                                placeholder="e.g. Acme Corp"
                                                className="mt-1 h-9"
                                            />
                                            <p className="text-[11px] text-muted-foreground mt-1">
                                                Replaces {`{{company_name}}`} throughout greeting and system prompt.
                                            </p>
                                        </div>

                                        <div className="min-w-0 break-words bg-muted/40 rounded-lg p-3 border space-y-2">
                                            <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                                                <Volume2 className="h-3.5 w-3.5 text-primary" />
                                                Suggested Tone & Persona
                                            </div>
                                            <p className="text-xs leading-relaxed text-foreground/75">
                                                <span className="font-semibold text-foreground">Tone:</span>{' '}
                                                {selectedTemplate.suggestedVoiceTone}
                                            </p>
                                            <p className="text-xs leading-relaxed text-foreground/75">
                                                <span className="font-semibold text-foreground">Persona:</span>{' '}
                                                {selectedTemplate.suggestedPersonality}
                                            </p>
                                        </div>

                                        <div className="space-y-1.5">
                                            <Label className="text-xs font-semibold">Included Features</Label>
                                            <div className="flex flex-wrap gap-1.5">
                                                {selectedTemplate.features.map((feat) => (
                                                    <Badge
                                                        key={feat}
                                                        variant="secondary"
                                                        className="max-w-full whitespace-normal break-words text-left text-[11px] font-normal leading-snug"
                                                    >
                                                        <Check className="h-3 w-3 mr-1 text-emerald-600" />
                                                        {feat}
                                                    </Badge>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Right Column: Prompt & Greeting Preview */}
                                <div className="min-w-0 space-y-4">
                                    <div className="space-y-1.5">
                                        <Label className="text-xs font-semibold flex items-center gap-1.5">
                                            <MessageSquare className="h-3.5 w-3.5 text-primary" />
                                            Spoken First Message
                                        </Label>
                                        <div className="min-w-0 break-words bg-muted/40 p-3 rounded-lg border text-sm leading-relaxed text-foreground italic">
                                            &ldquo;
                                            {templatePreview?.nodes[0].data.greeting || 'The agent will generate a brief greeting in the selected language when the call starts.'}
                                            &rdquo;
                                        </div>
                                    </div>

                                    <div className="space-y-1.5">
                                        <Label className="text-xs font-semibold flex items-center gap-1.5">
                                            <Sparkles className="h-3.5 w-3.5 text-primary" />
                                            System Instructions Preview
                                        </Label>
                                        <div className="min-w-0 max-h-56 overflow-y-auto whitespace-pre-wrap break-words rounded-lg border bg-muted/30 p-3 text-xs font-mono leading-relaxed text-foreground/80">
                                            {templatePreview?.nodes[0].data.prompt}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    ) : (
                        /* Grid of Templates */
                        <div className="grid min-w-0 grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                            {filteredTemplates.map((template) => {
                                const IconComponent = getTemplateIcon(template.icon);
                                const colorStyles = COLOR_MAP[template.color] || COLOR_MAP.slate;

                                return (
                                    <Card
                                        key={template.id}
                                        onClick={() => handleSelectTemplate(template)}
                                        className="group relative flex min-w-0 flex-col justify-between overflow-hidden rounded-xl border p-4 transition-all duration-200 hover:border-primary/50 hover:shadow-md"
                                    >
                                        <div className="min-w-0">
                                            <div className="mb-3 flex min-w-0 items-start justify-between gap-2">
                                                <div
                                                    className={`h-10 w-10 rounded-xl flex items-center justify-center transition-transform group-hover:scale-105 ${colorStyles.iconBg}`}
                                                >
                                                    <IconComponent className="h-5 w-5" />
                                                </div>
                                                <Badge
                                                    variant="secondary"
                                                    className={`max-w-[65%] whitespace-normal break-words text-right text-[10px] uppercase font-semibold tracking-wider leading-snug ${colorStyles.bg} ${colorStyles.text}`}
                                                >
                                                    {template.badge}
                                                </Badge>
                                            </div>

                                            <h4 className="break-words text-sm font-semibold leading-snug text-foreground transition-colors group-hover:text-primary">
                                                {template.name}
                                            </h4>
                                            <p className="mt-1 line-clamp-3 break-words text-[13px] leading-relaxed text-foreground/75">
                                                {template.description}
                                            </p>

                                            <div className="mt-3 flex min-w-0 flex-wrap gap-1">
                                                {template.features.slice(0, 2).map((feat) => (
                                                    <span
                                                        key={feat}
                                                        className="inline-flex max-w-full items-center break-words rounded bg-muted px-1.5 py-0.5 text-[10px] leading-snug text-foreground/80"
                                                    >
                                                        {feat}
                                                    </span>
                                                ))}
                                                {template.features.length > 2 && (
                                                    <span className="self-center text-[10px] text-foreground/75">
                                                        +{template.features.length - 2} more
                                                    </span>
                                                )}
                                            </div>
                                        </div>

                                        <div className="mt-4 flex min-w-0 flex-wrap items-center justify-between gap-2 border-t pt-3 text-xs font-medium text-primary">
                                            <span>Customize & Deploy</span>
                                            <span className="transition-transform group-hover:translate-x-1">
                                                &rarr;
                                            </span>
                                        </div>
                                    </Card>
                                );
                            })}
                        </div>
                    )}
                </div>

                <DialogFooter className="shrink-0 border-t bg-muted/20 px-6 py-4 flex items-center justify-between">
                    {selectedTemplate ? (
                        <>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={handleClosePreview}
                                disabled={isDeploying}
                            >
                                Back
                            </Button>
                            <Button
                                onClick={handleDeploy}
                                disabled={isDeploying || !customAgentName.trim()}
                                className="bg-primary hover:bg-primary/90"
                            >
                                {isDeploying ? (
                                    <>
                                        <div className="h-4 w-4 mr-2 animate-spin rounded-full border-2 border-current border-t-transparent" />
                                        Creating Agent...
                                    </>
                                ) : (
                                    <>
                                        <Sparkles className="h-4 w-4 mr-2" />
                                        Use This Template
                                    </>
                                )}
                            </Button>
                        </>
                    ) : (
                        <div className="w-full flex items-center justify-between text-xs text-muted-foreground">
                            <span>Showing {filteredTemplates.length} templates</span>
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => onOpenChange(false)}
                            >
                                Cancel
                            </Button>
                        </div>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
