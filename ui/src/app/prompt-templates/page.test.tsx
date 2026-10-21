import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ templates: vi.fn(), createTemplate: vi.fn(), createAgent: vi.fn(), push: vi.fn() }));
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ user: { id: 'user-1' }, loading: false }) }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/lib/kodewavesApi', () => ({ promptTemplatesApi: { getTemplates: mocks.templates, createTemplate: mocks.createTemplate } }));
vi.mock('@/client/sdk.gen', () => ({ createWorkflowApiV1WorkflowCreateDefinitionPost: mocks.createAgent }));
import PromptTemplatesPage from './page';
import { promptTemplateWorkflow } from '@/lib/promptTemplateWorkflow';

const template = { id: 'saved-template', title: 'Customer help', category: 'Support', description: 'Help customers', system_prompt: 'Answer questions about our configured services.', first_message: 'नमस्ते, कैसे मदद करूँ?', tags: [], is_featured: false };

describe('saved prompt template agent creation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.templates.mockResolvedValue([template]);
    mocks.createAgent.mockResolvedValue({ data: { id: 42 } });
  });

  it('creates an editable agent with the saved prompt and exact greeting', async () => {
    render(<PromptTemplatesPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Use in Voice Studio' }));
    await waitFor(() => expect(mocks.createAgent).toHaveBeenCalledTimes(1));
    const body = mocks.createAgent.mock.calls[0][0].body;
    expect(body.name).toBe('Customer help');
    expect(body.workflow_definition.nodes.map((node: any) => node.type)).toEqual(['startCall', 'endCall']);
    expect(body.workflow_definition.nodes[0].data.greeting).toBe(template.first_message);
    expect(body.workflow_definition.nodes[0].data.prompt).toBe(template.system_prompt);
    expect(body.workflow_definition.edges).toHaveLength(1);
    expect(body.workflow_definition.edges[0].data.label).toBe('finish_call');
    expect(body.workflow_definition).not.toHaveProperty('template_language');
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith('/workflow/42?onboarding=web_call'));
  });

  it('shows a failed creation instead of navigating to the agent list', async () => {
    mocks.createAgent.mockResolvedValue({ error: { detail: 'Agent creation unavailable' } });
    render(<PromptTemplatesPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Use in Voice Studio' }));
    expect((await screen.findByRole('alert')).textContent).toContain('Agent creation unavailable');
    expect(mocks.push).not.toHaveBeenCalled();
  });
});

it('turns a shared delivery template into an honest, speakable agent', () => {
  const workflow = promptTemplateWorkflow({
    system_prompt: 'You help callers for {{company_name}}. Track shipments when possible.',
    first_message: 'Hi! Thank you for calling {{company_name}} delivery support. Share your tracking number so I can look up your shipment.',
    is_featured: true,
  });
  const start = workflow.nodes[0].data;
  expect(start.greeting).toBe('Hi! Thank you for calling delivery support. Share your tracking number so I can guide you.');
  expect(start.prompt).toContain('A matching connected tool is required');
  expect(start.prompt).not.toContain('{{company_name}}');
  expect(start.greeting).not.toContain('{{company_name}}');
});
