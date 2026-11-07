import { cleanup, render, screen } from '@testing-library/react';
import type { PropsWithChildren } from 'react';
import { afterEach, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ createWorkflow: vi.fn(), createFolder: vi.fn(), token: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ user: { id: 1 }, getAccessToken: api.token }) }));
vi.mock('@/client/sdk.gen', () => ({
    createWorkflowApiV1WorkflowCreateDefinitionPost: api.createWorkflow,
    createFolderApiV1FolderPost: api.createFolder,
}));
vi.mock('@/components/ui/dialog', () => ({
    Dialog: ({ children }: PropsWithChildren) => <div>{children}</div>,
    DialogContent: ({ children }: PropsWithChildren) => <div>{children}</div>,
    DialogHeader: ({ children }: PropsWithChildren) => <div>{children}</div>,
    DialogTitle: ({ children }: PropsWithChildren) => <h2>{children}</h2>,
}));
vi.mock('@/components/workflow/folders/FolderFormDialog', () => ({ FolderFormDialog: () => null }));
vi.mock('@/components/workflow/TemplateSelectorModal', () => ({ TemplateSelectorModal: () => null }));

import { CreateWorkflowButton } from '@/components/workflow/CreateWorkflowButton';
import { CreateFolderButton } from '@/components/workflow/folders/CreateFolderButton';
import { UploadWorkflowButton } from '@/components/workflow/UploadWorkflowButton';

afterEach(cleanup);

it('marks each agent-library action explicitly so hero contrast does not depend on sibling order', () => {
    render(<>
        <UploadWorkflowButton />
        <CreateFolderButton />
        <CreateWorkflowButton />
    </>);

    const upload = screen.getByRole('button', { name: /Upload Agent Definition/ });
    const folder = screen.getByRole('button', { name: /New Folder/ });
    expect(upload.getAttribute('data-hero-action')).toBe('upload');
    expect(upload.className).not.toMatch(/#(?:d1b367|dec783|17271f)/i);
    expect(upload.querySelector('[data-hero-label]')?.textContent).toBe('Upload Agent Definition');
    expect(folder.getAttribute('data-hero-action')).toBe('folder');
    expect(folder.className).toContain('!text-[#edf2e9]');
    expect(folder.querySelector('[data-hero-label]')?.textContent).toBe('New Folder');
    const create = screen.getByRole('button', { name: /Create Agent/ });
    expect(create.getAttribute('data-hero-action')).toBe('create');
    expect(create.querySelector('[data-hero-label]')?.textContent).toBe('Create Agent');
});
