'use client';

import {
    ArrowRight,
    Calendar,
    PhoneCall,
    Plus,
    Sparkles,
    TrendingUp,
} from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { TemplateSelectorModal } from '@/components/workflow/TemplateSelectorModal';
import { AGENT_TEMPLATES, AgentTemplate } from '@/constants/agentTemplates';
import chrome from "@/components/layout/WorkspaceChrome.module.css";

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
            <div className={chrome.emptyState}>
                <div className={chrome.emptyHeader}>
                    <span className="mb-3 block font-mono text-[10px] uppercase tracking-widest text-primary">YOUR FIRST VOICE WORKFLOW</span>
                    <h3>Start with the conversation you need.</h3>
                    <p>Choose a starting template, then configure its instructions, voice and tools. Test it in the browser before connecting your phone line.</p>
                </div>
                <div className={chrome.templates}>
                    {featuredTemplates.map((template) => {
                        const IconComponent = template.id === 'receptionist' ? PhoneCall : template.id === 'appointment-booking' ? Calendar : TrendingUp;
                        return <button type="button" key={template.id} className={chrome.template} onClick={() => handleOpenFeatured(template)}><IconComponent size={23} /><strong>{template.name}</strong><p>{template.description}</p><span>Explore template <ArrowRight size={15} /></span></button>;
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
