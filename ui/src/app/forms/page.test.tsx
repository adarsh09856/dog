import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ getForms: vi.fn(), getSubmissions: vi.fn(), createForm: vi.fn(), updateForm: vi.fn(), user: { id: 'user-1' } }));
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ user: mocks.user, loading: false }) }));
vi.mock('@/lib/kodewavesApi', () => ({ formsApi: mocks }));
import FormsPage from './page';

describe('form builder and submissions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.user = { id: 'user-1' };
    mocks.getForms.mockResolvedValue([]);
    mocks.createForm.mockResolvedValue({ id: 'form-1' });
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
    mocks.getSubmissions.mockRejectedValue(new Error('Submission service unavailable'));
    render(<FormsPage />);
    const row = (await screen.findByText('Customer intake')).closest('tr')!;
    fireEvent.click(within(row).getByRole('button', { name: '1 leads' }));
    expect((await screen.findByRole('alert')).textContent).toContain('Submission service unavailable');
    expect(screen.queryByText('No submissions received yet for this form.')).toBeNull();
  });

  it('ignores a previous workspace list that finishes after switching identity', async () => {
    let finishOld!: (value: unknown[]) => void;
    mocks.getForms.mockReturnValueOnce(new Promise(resolve => { finishOld = resolve; })).mockResolvedValue([]);
    const view = render(<FormsPage />);
    await waitFor(() => expect(mocks.getForms).toHaveBeenCalledOnce());
    mocks.user = { id: 'user-2' };
    view.rerender(<FormsPage />);
    await waitFor(() => expect(mocks.getForms).toHaveBeenCalledTimes(2));
    await act(async () => finishOld([{ id: 'old', title: 'Old workspace form', slug: 'old', fields: [], is_active: true }]));
    expect(screen.queryByText('Old workspace form')).toBeNull();
  });

  it('does not overwrite the current form with an earlier submission response', async () => {
    let finishOld!: (value: unknown[]) => void;
    mocks.getForms.mockResolvedValue(['A', 'B'].map(id => ({ id, title: `Form ${id}`, slug: id, fields: [], is_active: true, submission_count: 1 })));
    mocks.getSubmissions.mockReturnValueOnce(new Promise(resolve => { finishOld = resolve; })).mockResolvedValue([{ id: 'b', data: { note: 'Current response B' }, created_at: '2026-10-20T00:00:00Z' }]);
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
