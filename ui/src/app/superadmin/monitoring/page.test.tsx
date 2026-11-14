import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ calls: vi.fn(), resources: vi.fn(), processHealth: vi.fn(), kill: vi.fn() }));
vi.mock('@/lib/kodewavesApi', () => ({ adminApi: {
    getLiveCalls: mocks.calls, getSystemResources: mocks.resources, getProcessHealth: mocks.processHealth, killCall: mocks.kill,
} }));
import Page from './page';

afterEach(cleanup);
beforeEach(() => {
    vi.clearAllMocks();
    mocks.calls.mockResolvedValue([]);
    mocks.resources.mockRejectedValue(new Error('Resource probe failed'));
    mocks.processHealth.mockResolvedValue({ status: 'healthy', timestamp: '2026-11-14T12:00:00Z', services: {
        database: { name: 'PostgreSQL', status: 'healthy', latency_ms: 2.3 },
        api_worker: { name: 'FastAPI Worker', status: 'healthy' },
    } });
});

it('checks platform process health only when requested and displays returned services', async () => {
    render(<Page />);
    expect(mocks.processHealth).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Check service health' }));
    expect(await screen.findByText('PostgreSQL')).toBeTruthy();
    expect(screen.getByText('2.3 ms')).toBeTruthy();
    expect(screen.getByText('FastAPI Worker')).toBeTruthy();
    expect(mocks.processHealth).toHaveBeenCalledTimes(1);
});

it('reports unavailable measurements and recovers with genuine zero values', async () => {
    render(<Page />);
    expect((await screen.findByRole('alert')).textContent).toContain('resource measurements are unavailable');
    expect(screen.queryByText('Adequate')).toBeNull();
    expect(screen.queryByText('Operating within limits')).toBeNull();
    mocks.resources.mockResolvedValue({ memory_percent: 0, memory_used_mb: 0,
        disk_free_gb: 0, disk_usage_percent: 0, active_concurrency: 0, concurrency_cap: 2, queue_size: 0 });
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(screen.getByText('0 MB used')).toBeTruthy();
    expect(screen.getByText('0 GB')).toBeTruthy();
});

it('does not overlap a slow polling request when Refresh is clicked', () => {
    mocks.calls.mockReturnValue(new Promise(() => {}));
    render(<Page />);
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(mocks.calls).toHaveBeenCalledTimes(1);
});
