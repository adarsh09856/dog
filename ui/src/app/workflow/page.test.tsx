import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { ReactElement } from 'react';

const api = vi.hoisted(() => ({ agents: vi.fn(), folders: vi.fn().mockResolvedValue({data: []}) }));
vi.mock('@/client/sdk.gen', () => ({ getWorkflowsApiV1WorkflowFetchGet: api.agents, listFoldersApiV1FolderGet: api.folders }));
vi.mock('@/lib/auth/server', () => ({ getServerAuthProvider: async () => 'local', getServerAccessToken: async () => 'synthetic' }));
vi.mock('@/lib/logger', () => ({default: {error: vi.fn()}}));
vi.mock('./WorkflowLayout', () => ({default: () => null}));
vi.mock('@/components/workflow/CreateWorkflowButton', () => ({CreateWorkflowButton: () => null}));
vi.mock('@/components/workflow/UploadWorkflowButton', () => ({UploadWorkflowButton: () => null}));
vi.mock('@/components/workflow/folders/CreateFolderButton', () => ({CreateFolderButton: () => null}));
vi.mock('@/components/workflow/folders/FolderSection', () => ({FolderSection: () => null}));
vi.mock('@/components/workflow/folders/AgentFolderView', () => ({AgentFolderView: () => <p>Existing agents</p>}));
vi.mock('@/components/workflow/EmptyWorkflowState', () => ({EmptyWorkflowState: () => <p>No agents yet</p>}));
import Page from './page';

async function renderServerPage() {
    const root = Page();
    const suspense = root.props.children as ReactElement<{children: ReactElement}>;
    const content = suspense.props.children;
    const resolve = content.type as (props: unknown) => Promise<ReactElement>;
    render(await resolve(content.props));
}

afterEach(cleanup);
it('shows resolved HTTP failures instead of falsely claiming there are no agents', async () => {
    api.agents.mockResolvedValue({error: {detail: [{msg: 'Agent service unavailable'}]}});
    await renderServerPage();
    expect(screen.getByRole('alert').textContent).toContain('Agent service unavailable');
    expect(screen.getByRole('link', {name: 'Retry loading agents'}).getAttribute('href')).toBe('/workflow');
    expect(screen.queryByText('No agents yet')).toBeNull();
});
it('keeps a successful empty result distinct from a failure', async () => {
    api.agents.mockResolvedValue({data: []});
    await renderServerPage();
    expect(screen.getByText('No agents yet')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
});
