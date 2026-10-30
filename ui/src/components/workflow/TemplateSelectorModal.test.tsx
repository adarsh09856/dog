import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  createWorkflow: vi.fn(),
  push: vi.fn(),
}));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/lib/auth', () => ({
  useAuth: () => ({ user: { id: 1 }, getAccessToken: vi.fn().mockResolvedValue('test-token') }),
}));
vi.mock('@/client/sdk.gen', () => ({
  createWorkflowApiV1WorkflowCreateDefinitionPost: mocks.createWorkflow,
}));
vi.mock('@/lib/templateLanguage', () => ({ configuredTemplateLanguage: vi.fn().mockResolvedValue(null) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/logger', () => ({ default: { error: vi.fn() } }));

import { TemplateSelectorModal } from './TemplateSelectorModal';

describe('TemplateSelectorModal', () => {
  beforeEach(() => {
    mocks.createWorkflow.mockReset().mockResolvedValue({ data: { id: 42 } });
    mocks.push.mockReset();
  });

  it('keeps filtering and selection usable while containing long card content', async () => {
    render(<TemplateSelectorModal open onOpenChange={vi.fn()} />);

    const receptionist = screen.getByText('Virtual Receptionist & Front Desk');
    const card = receptionist.closest('[data-slot="card"]');
    expect(card).toBeTruthy();
    expect(card?.className).toContain('min-w-0');
    expect(receptionist.className).toContain('break-words');

    fireEvent.change(screen.getByPlaceholderText('Search templates by role, feature, or keyword...'), {
      target: { value: 'BANT criteria' },
    });
    expect(screen.getByText('Lead Qualification & SDR')).toBeTruthy();
    expect(screen.queryByText('Virtual Receptionist & Front Desk')).toBeNull();

    const search = screen.getByPlaceholderText('Search templates by role, feature, or keyword...');
    fireEvent.change(search, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sales & Lead Gen' }));
    expect(screen.getByText('Lead Qualification & SDR')).toBeTruthy();
    expect(screen.queryByText('Virtual Receptionist & Front Desk')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'All Templates' }));
    fireEvent.click(screen.getByText('Virtual Receptionist & Front Desk'));
    await waitFor(() => expect(screen.getByLabelText('Agent Name')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: 'Use This Template' }));
    await waitFor(() => expect(mocks.createWorkflow).toHaveBeenCalledWith(expect.objectContaining({
      body: expect.objectContaining({ name: 'Virtual Receptionist & Front Desk' }),
    })));
    expect(mocks.push).toHaveBeenCalledWith('/workflow/42?onboarding=web_call');
  });

  it('uses the workspace green palette for appointment templates', () => {
    render(<TemplateSelectorModal open onOpenChange={vi.fn()} />);

    const appointment = screen.getByText('Appointment Setter & Scheduling');
    const card = appointment.closest('[data-slot="card"]');
    expect(card).toBeTruthy();
    expect(card?.querySelector('.bg-emerald-500')).toBeTruthy();
    expect(card?.querySelector('.bg-emerald-50')).toBeTruthy();
    expect(card?.querySelector('.text-emerald-700')).toBeTruthy();
    expect(card?.querySelector('.bg-blue-500, .bg-blue-50, .text-blue-700')).toBeNull();
  });
});
