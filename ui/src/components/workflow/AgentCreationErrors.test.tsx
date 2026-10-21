import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ create: vi.fn(), duplicate: vi.fn(), token: vi.fn(), push: vi.fn(), error: vi.fn(), catalog: vi.fn(), user: { id: 1 } as { id: number } | null, loading: false }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ user: mocks.user, loading: mocks.loading, getAccessToken: mocks.token }) }));
vi.mock('@/client/sdk.gen', () => ({ createWorkflowApiV1WorkflowCreateDefinitionPost: mocks.create, duplicateWorkflowTemplateApiV1WorkflowTemplatesDuplicatePost: mocks.duplicate }));
vi.mock('sonner', () => ({ toast: { error: mocks.error, success: vi.fn() } }));
vi.mock('@/lib/kodewavesApi', () => ({ catalogApi: { getAvailableCatalog: mocks.catalog }, apiFetch: vi.fn() }));
vi.mock('@/lib/templateLanguage', () => ({ configuredTemplateLanguage: vi.fn().mockResolvedValue('en') }));
vi.mock('@/lib/logger', () => ({ default: { error: vi.fn(), info: vi.fn() } }));
vi.mock('@/components/workflow/TemplateSelectorModal', () => ({ TemplateSelectorModal: () => null }));
vi.mock('@/components/ui/dropdown-menu', () => ({
    DropdownMenu: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
    DropdownMenuContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
    DropdownMenuTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
    DropdownMenuItem: ({ children, onClick }: React.PropsWithChildren<{ onClick?: () => void }>) => <button onClick={onClick}>{children}</button>,
    DropdownMenuSeparator: () => null,
}));

import { CreateWorkflowButton } from './CreateWorkflowButton';
import { DuplicateWorkflowTemplate } from './TemplateCard';
import CreateWorkflowPage from '@/app/workflow/create/page';

beforeEach(() => {
    vi.clearAllMocks();
    mocks.token.mockResolvedValue('test-session');
    mocks.user = { id: 1 };
    mocks.loading = false;
    mocks.catalog.mockResolvedValue({ local_llm_models: [{ id: 'local' }] });
});

describe.each(['blank', 'template', 'builder blank'] as const)('%s agent creation', (kind) => {
    function start() {
        if (kind === 'blank') {
            render(<CreateWorkflowButton />);
            fireEvent.click(screen.getByText('Blank Canvas'));
        } else if (kind === 'template') {
            render(<DuplicateWorkflowTemplate id={4} title="Support" description="Customer support" />);
            fireEvent.click(screen.getByText('Duplicate Workflow Template'));
        } else {
            render(<CreateWorkflowPage />);
            fireEvent.click(screen.getByText('Start Blank Canvas'));
        }
    }
    const request = () => kind === 'template' ? mocks.duplicate : mocks.create;

    it('shows a resolved API rejection instead of silently doing nothing', async () => {
        request().mockResolvedValue({ error: { detail: 'Choose a matching voice before creating this agent.' } });
        start();
        await waitFor(() => expect(mocks.error).toHaveBeenCalledWith('Choose a matching voice before creating this agent.'));
        expect(mocks.push).not.toHaveBeenCalled();
    });

    it('does not send an unauthenticated create request after token expiry', async () => {
        mocks.token.mockResolvedValue(null);
        start();
        await waitFor(() => expect(mocks.error).toHaveBeenCalledWith('Your session has expired. Please sign in again.'));
        expect(request()).not.toHaveBeenCalled();
    });

    it('opens the returned agent after successful persistence', async () => {
        request().mockResolvedValue({ data: { id: 42 } });
        start();
        await waitFor(() => expect(mocks.push).toHaveBeenCalledWith('/workflow/42'));
        expect(mocks.error).not.toHaveBeenCalled();
    });
});

it('waits for authenticated identity before loading the creation catalog', async () => {
    mocks.user = null;
    mocks.loading = true;
    const view = render(<CreateWorkflowPage />);
    expect(mocks.catalog).not.toHaveBeenCalled();
    mocks.user = { id: 1 };
    mocks.loading = false;
    view.rerender(<CreateWorkflowPage />);
    await waitFor(() => expect(mocks.catalog).toHaveBeenCalledOnce());
});
