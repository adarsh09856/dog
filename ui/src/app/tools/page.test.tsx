import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({list: vi.fn(), token: vi.fn().mockResolvedValue('synthetic'), user: {id: 1}, push: vi.fn(), login: vi.fn()}));
vi.mock('@/client/sdk.gen', () => ({listToolsApiV1ToolsGet: mocks.list, createToolApiV1ToolsPost: vi.fn(), deleteToolApiV1ToolsToolUuidDelete: vi.fn(), getWorkflowsSummaryApiV1WorkflowSummaryGet: vi.fn(), unarchiveToolApiV1ToolsToolUuidUnarchivePost: vi.fn()}));
vi.mock('@/lib/auth', () => ({useAuth: () => ({user: mocks.user, loading: false, getAccessToken: mocks.token, redirectToLogin: mocks.login})}));
vi.mock('next/navigation', () => ({useRouter: () => ({push: mocks.push})}));
vi.mock('@/components/http', () => ({CredentialSelector: () => null}));
import Page from './page';
afterEach(cleanup);
it('shows tool query failure instead of the empty state and supports retry', async () => {
    mocks.list.mockResolvedValueOnce({error: {detail: 'Tools unavailable'}}).mockResolvedValue({data: []});
    render(<Page />);
    expect((await screen.findByRole('alert')).textContent).toContain('Tools unavailable');
    expect(screen.queryByText('No tools found')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Retry'}));
    expect(await screen.findByText('No tools found')).toBeTruthy();
});
