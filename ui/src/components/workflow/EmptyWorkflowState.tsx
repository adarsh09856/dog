'use client';

import {
    ArrowRight,
    Calendar,
    Check,
    PhoneCall,
    Plus,
    Sparkles,
    TrendingUp,
} from 'lucide-react';
import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { TemplateSelectorModal } from '@/components/workflow/TemplateSelectorModal';
import { AGENT_TEMPLATES, AgentTemplate } from '@/constants/agentTemplates';

const FEATURED_TEMPLATE_IDS = ['receptionist', 'appointment-booking', 'lead-qualification'];

export function EmptyWorkflowState() {
    const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);
    const [preselectedTemplate, setPreselectedTemplate] = useState<AgentTemplate | null>(null);

    const featuredTemplates = AGENT_TEMPLATES.filter((tpl) =>
        FEATURED_TEMPLATE_IDS.includes(tpl.id)
    );

    const handleOpenFeatured = (tpl: AgentTemplate) => {
        setPreselectedTemplate(tpl);
        setIsTemplateModalOpen(true);
    };

    const handleOpenAllTemplates = () => {
        setPreselectedTemplate(null);
        setIsTemplateModalOpen(true);
    };

    return (
        <>
            <div className="rounded-2xl border bg-card p-6 md:p-8 space-y-6">
                <div className="text-center max-w-xl mx-auto space-y-2">
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-semibold mb-2">
                        <Sparkles className="w-3.5 h-3.5" />
                        Quick Start with Templates
                    </div>
                    <h3 className="text-2xl font-bold tracking-tight">
                        Deploy your first AI Voice Agent in seconds
                    </h3>
                    <p className="text-sm text-muted-foreground">
                        Get started with one of our pre-built, industry-tuned templates or browse the full library.
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                    {featuredTemplates.map((template) => {
                        const IconComponent =
                            template.id === 'receptionist'
                                ? PhoneCall
                                : template.id === 'appointment-booking'
                                  ? Calendar
                                  : TrendingUp;

                        return (
                            <Card
                                key={template.id}
                                className="group relative flex flex-col justify-between hover:shadow-md transition-all duration-200 border cursor-pointer hover:border-primary/50"
                                onClick={() => handleOpenFeatured(template)}
                            >
                                <CardHeader className="pb-3">
                                    <div className="flex items-center justify-between mb-2">
                                        <div className="h-9 w-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center transition-transform group-hover:scale-105">
                                            <IconComponent className="h-4.5 w-4.5" />
                                        </div>
                                        <Badge variant="secondary" className="text-[10px] font-semibold">
                                            {template.badge}
                                        </Badge>
                                    </div>
                                    <CardTitle className="text-sm group-hover:text-primary transition-colors">
                                        {template.name}
                                    </CardTitle>
                                    <CardDescription className="text-xs line-clamp-2">
                                        {template.description}
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="pt-0 space-y-3">
                                    <div className="flex flex-wrap gap-1">
                                        {template.features.slice(0, 2).map((feat) => (
                                            <span
                                                key={feat}
                                                className="inline-flex items-center text-[10px] bg-muted px-1.5 py-0.5 rounded text-muted-foreground"
                                            >
                                                <Check className="w-2.5 h-2.5 mr-1 text-emerald-500" />
                                                {feat}
                                            </span>
                                        ))}
                                    </div>
                                    <div className="pt-2 border-t flex items-center justify-between text-xs text-primary font-medium">
                                        <span>Use Template</span>
                                        <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-1" />
                                    </div>
                                </CardContent>
                            </Card>
                        );
                    })}
                </div>

                <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
                    <Button
                        onClick={handleOpenAllTemplates}
                        className="w-full sm:w-auto gap-2 bg-primary hover:bg-primary/90"
                    >
                        <Sparkles className="w-4 h-4" />
                        Browse All {AGENT_TEMPLATES.length} Templates
                    </Button>
                    <Button
                        variant="outline"
                        onClick={() => window.location.assign('/workflow/create')}
                        className="w-full sm:w-auto gap-1.5"
                    >
                        <Plus className="w-4 h-4" />
                        Create Custom Agent
                    </Button>
                </div>
            </div>

            <TemplateSelectorModal
                open={isTemplateModalOpen}
                onOpenChange={setIsTemplateModalOpen}
            />
        </>
    );
}
