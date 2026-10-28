import { describe, expect, it } from 'vitest';
import { AGENT_TEMPLATES, generateTemplateWorkflowDefinition } from './agentTemplates';
import { INDIAN_TEMPLATE_LANGUAGES } from './languages';
import { promptTemplateWorkflow } from '../lib/promptTemplateWorkflow';

describe('built-in template conversation graphs', () => {
    it('keeps supplied caller details in shared featured support templates', () => {
        const graph = promptTemplateWorkflow({
            system_prompt: 'Always ask for the order ID or tracking number first.',
            is_featured: true,
        });
        expect(graph.nodes[0].data.prompt).toContain('never ask for the same detail again');
        expect(graph.nodes[0].data.prompt).toContain('cannot see the current shipment status');
        expect(graph.nodes[0].data.prompt).toContain('never claim to record, save, or pass details to staff');
        expect(graph.nodes[0].data.prompt).not.toContain('offer to pass the details to staff');
    });
    it('limits greetings to the opening and honors caller language changes across templates', () => {
        for (const template of AGENT_TEMPLATES) {
            for (const { code } of INDIAN_TEMPLATE_LANGUAGES) {
                const graph = generateTemplateWorkflowDefinition(template, { language: code });
                for (const node of graph.nodes.filter(n => n.type !== 'endCall')) {
                    expect(node.data.prompt).toContain('only when opening the conversation');
                    expect(node.data.prompt).toContain('Do not repeat the greeting on later turns');
                    expect(node.data.prompt).toContain('If the caller asks to switch language, follow that request');
                }
            }
        }
    });
    it('does not teach Hindi appointment agents to ignore English requests', () => {
        const graph = generateTemplateWorkflowDefinition(AGENT_TEMPLATES.find(t => t.id === 'appointment-booking')!, { language: 'hi' });
        expect(graph.nodes[0].data.prompt).toContain('Assistant: Sure. What date and time would you prefer?');
    });
    it('grounds support follow-ups in the latest caller message without promising unavailable actions', () => {
        const template = AGENT_TEMPLATES.find(t => t.id === 'customer-support')!;
        const graph = generateTemplateWorkflowDefinition(template, { language: 'hi', agentName: 'Asha' });
        const prompt = graph.nodes[0].data.prompt;
        expect(prompt).toContain('newest message');
        expect(prompt).toContain('Never repeat a previous reply');
        expect(prompt).toContain('Do not assume account access');
        expect(prompt).toContain('only after the tool succeeds');
    });
    it('keeps assistance on the conversational start node without a second routing model call', () => {
        for (const template of AGENT_TEMPLATES.filter(t => t.id !== 'blank-canvas')) {
            const graph = generateTemplateWorkflowDefinition(template);
            expect(graph.nodes.map(n => n.type)).toEqual(['startCall', 'endCall']);
            expect(graph.edges).toHaveLength(1);
            expect(graph.edges[0].source).toBe('1');
            expect(graph.edges[0].target).toBe('2');
            expect(graph.edges[0].data.label).toBe('finish_call');
            expect(graph.nodes[0].data.greeting_type).toBe('text');
            expect(graph.nodes[0].data.prompt).toContain('brief greeting');
        }
    });
    it('generates a Hindi/Hinglish opening and uses safe booking instructions for Hindi appointment templates', () => {
        const template = AGENT_TEMPLATES.find(t => t.id === 'appointment-booking')!;
        const graph = generateTemplateWorkflowDefinition(template, { language: 'hi', agentName: 'आशा' });
        expect(graph.template_language).toBe('hi');
            expect(graph.nodes[0].data.greeting).toContain('नमस्ते');
        expect(graph.nodes[0].data.prompt).toContain('booked=true');
        expect(graph.nodes[0].data.prompt).toContain('future date/time in IST');
        expect(graph.nodes[0].data.prompt).not.toContain('time and timezone');
        expect(graph.nodes[0].data.prompt).not.toContain('confirmation SMS/email will be sent');
    });

    it('uses the selected Indian language for the fast opening and normalizes regional Hindi codes', () => {
        const template = AGENT_TEMPLATES.find(t => t.id === 'customer-support')!;
        const regionalHindi = generateTemplateWorkflowDefinition(template, {
            language: 'hi-IN', agentName: 'Asha', companyName: 'Kodewaves',
        });
        expect(regionalHindi.nodes[0].data.greeting).toContain('नमस्ते');
        expect(regionalHindi.nodes[0].data.prompt).toContain('natural conversational Hindi');

        const english = generateTemplateWorkflowDefinition(template, {
            language: 'en', agentName: 'Asha', companyName: 'Kodewaves',
        });
        expect(english.nodes[0].data.greeting).toContain('Asha');
        expect(english.nodes[0].data.greeting).toContain('Kodewaves');
    });

    it('builds an agent prompt for every scheduled Indian language and permits code switching', () => {
        const template = AGENT_TEMPLATES.find(t => t.id === 'appointment-booking')!;
        expect(INDIAN_TEMPLATE_LANGUAGES).toHaveLength(22);
        for (const { code, name } of INDIAN_TEMPLATE_LANGUAGES) {
            const graph = generateTemplateWorkflowDefinition(template, { language: code });
            expect(graph.template_language).toBe(code);
            expect(String(graph.nodes[0].data.greeting ?? '').trim().length).toBeGreaterThan(0);
            expect(graph.nodes[0].data.prompt).toContain(name);
            expect(graph.nodes[0].data.prompt).toContain('brief greeting');
            expect(graph.nodes[0].data.prompt).toContain('override any conflicting language advice');
            expect(graph.nodes[0].data.prompt).toContain(code === 'hi' ? 'natural Hinglish' : 'natural English code-switching');
        }
    });
});
