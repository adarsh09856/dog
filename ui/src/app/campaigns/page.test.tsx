import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
    expect(await screen.findByText('No campaigns found')).toBeTruthy();
    expect(mocks.list).toHaveBeenCalledTimes(2);
});
