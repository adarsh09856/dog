import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ list: vi.fn(), token: vi.fn().mockResolvedValue('synthetic'), user: {id: 1}, push: vi.fn(), login: vi.fn() }));
vi.mock('@/client/sdk.gen', () => ({ getCampaignsApiV1CampaignGet: mocks.list }));
vi.mock('@/lib/auth', () => ({ useAuth: () => ({user: mocks.user, loading: false, getAccessToken: mocks.token, redirectToLogin: mocks.login}) }));
vi.mock('next/navigation', () => ({useRouter: () => ({push: mocks.push})}));
vi.mock('@/hooks/useOrganizationTimezone', () => ({useOrganizationTimezone: () => 'Asia/Kolkata'}));
import Page from './page';
afterEach(cleanup);
it('shows a resolved API failure and retries without pretending the campaign list is empty', async () => {
    mocks.list.mockResolvedValueOnce({error: {detail: 'Campaign service unavailable'}}).mockResolvedValue({data: {campaigns: []}});
    render(<Page />);
    expect((await screen.findByRole('alert')).textContent).toContain('Campaign service unavailable');
    expect(screen.queryByText('No campaigns found')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Retry'}));
    expect(await screen.findByText('No campaigns yet')).toBeTruthy();
    expect(mocks.list).toHaveBeenCalledTimes(2);
});

it('filters campaign cards by name, workflow, and state', async () => {
    mocks.list.mockResolvedValue({data: {campaigns: [
        {id: 1, name: 'Spring launch', workflow_name: 'Welcome flow', state: 'running', created_at: '2026-10-28T10:00:00Z', total_queued_count: 40, executed_count: 10, traffic_split: null},
        {id: 2, name: 'Winback', workflow_name: 'Return flow', state: 'completed', created_at: '2026-10-27T10:00:00Z', total_queued_count: 20, executed_count: 20, traffic_split: null},
    ]}});
    render(<Page />);
    expect(await screen.findByText('Spring launch')).toBeTruthy();
    expect(screen.getByText('Winback')).toBeTruthy();
    fireEvent.change(screen.getByRole('textbox', {name: 'Search campaigns'}), {target: {value: 'welcome'}});
    expect(screen.getByText('Spring launch')).toBeTruthy();
    expect(screen.queryByText('Winback')).toBeNull();
    fireEvent.change(screen.getByRole('combobox', {name: 'Filter campaigns by state'}), {target: {value: 'completed'}});
    fireEvent.change(screen.getByRole('textbox', {name: 'Search campaigns'}), {target: {value: ''}});
    expect(screen.getByText('Winback')).toBeTruthy();
    expect(screen.queryByText('Spring launch')).toBeNull();
});
