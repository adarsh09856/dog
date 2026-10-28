import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  auth: { loading: true, user: null as null | { id: string } },
  getContacts: vi.fn(), getStages: vi.fn(),
}));
vi.mock('@/lib/auth', () => ({ useAuth: () => mocks.auth }));
vi.mock('@/lib/kodewavesApi', () => ({ crmApi: mocks }));
import CRMPage from './page';

describe('CRM page loading', () => {
  beforeEach(() => {
    mocks.auth = { loading: true, user: null };
    mocks.getContacts.mockReset();
    mocks.getStages.mockReset();
  });
  it('waits for authentication, then tolerates contacts without a first name', async () => {
    mocks.getContacts.mockResolvedValue([{ id: 'contact-1', first_name: null, phone: '+15550123456' }]);
    mocks.getStages.mockResolvedValue([]);
    const view = render(<CRMPage />);
    expect(mocks.getContacts).not.toHaveBeenCalled();
    mocks.auth = { loading: false, user: { id: 'user-1' } };
    view.rerender(<CRMPage />);
    await screen.findByText('+15550123456');
    expect(mocks.getContacts).toHaveBeenCalledTimes(1);
  });
  it('shows a failed load instead of silently replacing server data', async () => {
    mocks.auth = { loading: false, user: { id: 'user-1' } };
    mocks.getContacts.mockRejectedValue(new Error('CRM unavailable'));
    mocks.getStages.mockResolvedValue([]);
    render(<CRMPage />);
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('CRM unavailable'));
  });
});
