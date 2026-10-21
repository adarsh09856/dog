import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ logs: vi.fn() }));
vi.mock('@/lib/kodewavesApi', () => ({ adminApi: { getAuditLogs: mocks.logs } }));
import Page from './page';

afterEach(cleanup);

it('distinguishes a failed audit query from a genuinely empty trail and retries', async () => {
    mocks.logs.mockRejectedValueOnce(new Error('Audit service unavailable')).mockResolvedValue([]);
    render(<Page />);
    expect((await screen.findByRole('alert')).textContent).toContain('Audit service unavailable');
    expect(screen.queryByText('No audit events recorded yet.')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(await screen.findByText('No audit events recorded yet.')).toBeTruthy();
});
