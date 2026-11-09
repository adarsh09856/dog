import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ getForms: vi.fn(), getSubmissionsPage: vi.fn(), createForm: vi.fn(), updateForm: vi.fn(), getPublicAccess: vi.fn(), setPublicAccess: vi.fn(), user: { id: 'user-1', is_superuser: false }, backendApiEndpoint: 'https://api.kodewaves.example' }));
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ user: mocks.user, loading: false }) }));
vi.mock('@/lib/kodewavesApi', () => ({ formsApi: mocks }));
vi.mock('@/context/AppConfigContext', () => ({ useAppConfig: () => ({ config: { backendApiEndpoint: mocks.backendApiEndpoint } }) }));
import FormsPage from './page';

describe('form builder and submissions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.user = { id: 'user-1', is_superuser: false };
    mocks.getForms.mockResolvedValue([]);
    mocks.getSubmissionsPage.mockResolvedValue({ submissions: [], total: 0 });
    mocks.createForm.mockResolvedValue({ id: 'form-1' });
    mocks.getPublicAccess.mockResolvedValue({ enabled: false, token_configured: false, allowed_origins: [] });
    mocks.setPublicAccess.mockResolvedValue({ enabled: true, token_configured: true, allowed_origins: ['https://example.com'], submission_token: 'one-time-token' });
  });

  it('saves optional and required questions from the builder', async () => {
    render(<FormsPage />);
    await waitFor(() => expect(mocks.getForms).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: 'Create Form' }));
    fireEvent.click(screen.getByRole('switch', { name: 'Require Full Name' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save Questionnaire' }));
    await waitFor(() => expect(mocks.createForm).toHaveBeenCalledWith(expect.objectContaining({
      fields: expect.arrayContaining([expect.objectContaining({ name: 'full_name', required: false })]),
    })));
  });

  it('shows submission errors without claiming the form has no responses', async () => {
    mocks.getForms.mockResolvedValue([{ id: 'form-1', title: 'Customer intake', slug: 'customer-intake', fields: [], is_active: true, submission_count: 1 }]);
    mocks.getSubmissionsPage.mockRejectedValue(new Error('Submission service unavailable'));
    render(<FormsPage />);
    const row = (await screen.findByText('Customer intake')).closest('tr')!;
    fireEvent.click(within(row).getByRole('button', { name: '1 leads' }));
    expect((await screen.findByRole('alert')).textContent).toContain('Submission service unavailable');
    expect(screen.queryByText('No submissions received yet for this form.')).toBeNull();
  });

  it('lets an authenticated organization user publish a form and shows the new token only after saving', async () => {
    mocks.user = { id: 'owner-1', is_superuser: false };
    mocks.getForms.mockResolvedValue([{ id: 'form-1', title: 'Customer intake', slug: 'customer-intake', fields: [], is_active: true, submission_count: 0 }]);
    render(<FormsPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Publish Customer intake on website' }));
    await waitFor(() => expect(mocks.getPublicAccess).toHaveBeenCalledWith('form-1'));
    fireEvent.click(await screen.findByRole('switch', { name: 'Enable public website submissions' }));
    fireEvent.change(screen.getByLabelText('Allowed website origins'), { target: { value: 'https://example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save publishing settings' }));
    await waitFor(() => expect(mocks.setPublicAccess).toHaveBeenCalledWith('form-1', {
      enabled: true,
      allowed_origins: ['https://example.com'],
      rotate_token: false,
    }));
    expect(await screen.findByLabelText('One-time submission token')).toBeTruthy();
    expect(screen.getByText(/will not be shown again after closing/i)).toBeTruthy();
    const snippet = screen.getByTestId('public-form-integration-snippet').textContent ?? '';
    expect(snippet).toContain('new URL("/api/v1/public/forms/form-1/submit", "https://api.kodewaves.example")');
    expect(snippet).not.toContain('window.location.origin');
  });

  it('requires an allowed website origin before publishing browser submissions', async () => {
    mocks.user = { id: 'owner-1', is_superuser: false };
    mocks.getForms.mockResolvedValue([{ id: 'form-1', title: 'Customer intake', slug: 'customer-intake', fields: [], is_active: true, submission_count: 0 }]);
    render(<FormsPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Publish Customer intake on website' }));
    fireEvent.click(await screen.findByRole('switch', { name: 'Enable public website submissions' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save publishing settings' }));
    expect((await screen.findByRole('alert')).textContent).toContain('Add at least one allowed website origin before publishing.');
    expect(mocks.setPublicAccess).not.toHaveBeenCalled();
  });

  it('ignores a previous workspace list that finishes after switching identity', async () => {
    let finishOld!: (value: unknown[]) => void;
    mocks.getForms.mockReturnValueOnce(new Promise(resolve => { finishOld = resolve; })).mockResolvedValue([]);
    const view = render(<FormsPage />);
    await waitFor(() => expect(mocks.getForms).toHaveBeenCalledOnce());
    mocks.user = { id: 'user-2', is_superuser: false };
    view.rerender(<FormsPage />);
    await waitFor(() => expect(mocks.getForms).toHaveBeenCalledTimes(2));
    await act(async () => finishOld([{ id: 'old', title: 'Old workspace form', slug: 'old', fields: [], is_active: true }]));
    expect(screen.queryByText('Old workspace form')).toBeNull();
  });

  it('does not overwrite the current form with an earlier submission response', async () => {
    let finishOld!: (value: unknown[]) => void;
    mocks.getForms.mockResolvedValue(['A', 'B'].map(id => ({ id, title: `Form ${id}`, slug: id, fields: [], is_active: true, submission_count: 1 })));
    mocks.getSubmissionsPage.mockReturnValueOnce(new Promise(resolve => { finishOld = resolve; })).mockResolvedValue({ submissions: [{ id: 'b', data: { note: 'Current response B' }, created_at: '2026-10-20T00:00:00Z' }], total: 1 });
    render(<FormsPage />);
    fireEvent.click(within((await screen.findByText('Form A')).closest('tr')!).getByRole('button', { name: '1 leads' }));
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    fireEvent.click(within(screen.getByText('Form B').closest('tr')!).getByRole('button', { name: '1 leads' }));
    await screen.findByText(/Current response B/);
    await act(async () => finishOld([{ id: 'a', data: { note: 'Stale response A' }, created_at: '2026-10-20T00:00:00Z' }]));
    expect(screen.queryByText(/Stale response A/)).toBeNull();
    expect(screen.getByText(/Current response B/)).toBeTruthy();
  });
});
