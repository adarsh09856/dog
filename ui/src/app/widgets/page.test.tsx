import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  auth: { loading: false, user: { id: 'user-1' } as { id: string } | null },
  getWidgets: vi.fn(), createWidget: vi.fn(), updateWidget: vi.fn(), deleteWidget: vi.fn(), agents: vi.fn(),
}));
vi.mock('@/lib/auth', () => ({ useAuth: () => mocks.auth }));
vi.mock('@/lib/kodewavesApi', () => ({ widgetsApi: mocks }));
vi.mock('@/client/sdk.gen', () => ({ getWorkflowsApiV1WorkflowFetchGet: mocks.agents }));
vi.mock('@/context/ClientBrandingContext', () => ({
  useClientBranding: () => ({ primary_color: '#116b4b' }),
}));
type MockSelectProps = {
  value?: string;
  onValueChange?: (value: string) => void;
  children?: ReactNode;
};
vi.mock('@/components/ui/select', () => ({
  Select: ({ value, onValueChange, children }: MockSelectProps) => <select value={value} onChange={(event) => onValueChange?.(event.target.value)}>{children}</select>,
  SelectTrigger: () => null, SelectValue: () => null,
  SelectContent: ({ children }: MockSelectProps) => <>{children}</>,
  SelectItem: ({ value, children }: MockSelectProps) => <option value={value}>{children}</option>,
}));
import WidgetsPage from './page';

describe('website widget flows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.auth = { loading: false, user: { id: 'user-1' } };
    mocks.getWidgets.mockResolvedValue([]);
    mocks.agents.mockResolvedValue({ data: [{ id: 10, name: 'Support agent', status: 'active' }] });
    mocks.createWidget.mockResolvedValue({ id: 'new-widget' });
    mocks.updateWidget.mockResolvedValue({ id: 'existing-widget' });
  });

  it('creates a widget with the selected agent and domain restrictions', async () => {
    render(<WidgetsPage />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create Widget' }).hasAttribute('disabled')).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: 'Create Widget' }));
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: '10' } });
    fireEvent.change(screen.getByPlaceholderText('example.com, www.example.com'), { target: { value: 'example.test, support.test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Widget' }));
    await waitFor(() => expect(mocks.createWidget).toHaveBeenCalledWith(expect.objectContaining({
      workflow_id: 10, allowed_domains: ['example.test', 'support.test'], is_active: true,
      primary_color: '#116b4b',
    })));
  });

  it('saves edited aliases without resending stale server aliases', async () => {
    mocks.getWidgets.mockResolvedValue([{
      id: 'existing-widget', name: 'Original widget', widget_name: 'Original widget', workflow_id: 10,
      welcome_message: 'Old button', bubble_title: 'Old button', primary_color: '#123456',
      position: 'bottom-left', is_active: false, allowed_domains: ['example.test'],
    }]);
    render(<WidgetsPage />);
    const row = (await screen.findByText('Original widget')).closest('tr')!;
    fireEvent.click(within(row).getAllByRole('button')[1]);
    fireEvent.change(screen.getByPlaceholderText('Product Landing Page Voice Button'), { target: { value: 'Renamed widget' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Widget' }));
    await waitFor(() => expect(mocks.updateWidget).toHaveBeenCalledWith('existing-widget', expect.objectContaining({ name: 'Renamed widget', is_active: false })));
    expect(mocks.updateWidget.mock.calls[0][1]).not.toHaveProperty('widget_name');
    expect(mocks.updateWidget.mock.calls[0][1]).not.toHaveProperty('bubble_title');
  });

  it('shows the runtime embed snippet returned by the server', async () => {
    const embedCode = '<script src="https://app.test/embed/kodewaves-widget.js?token=emb_test"></script>';
    mocks.getWidgets.mockResolvedValue([{ id: 'widget', name: 'Embed widget', workflow_id: 10, embed_code: embedCode }]);
    render(<WidgetsPage />);
    const row = (await screen.findByText('Embed widget')).closest('tr')!;
    fireEvent.click(within(row).getAllByRole('button')[0]);
    expect(await screen.findByText(embedCode)).toBeTruthy();
    expect(mocks.updateWidget).not.toHaveBeenCalled();
  });

  it('ignores a widget list from the previous authenticated workspace', async () => {
    let finishOld!: (value: unknown[]) => void;
    mocks.getWidgets.mockReturnValueOnce(new Promise(resolve => { finishOld = resolve; })).mockResolvedValue([]);
    const view = render(<WidgetsPage />);
    await waitFor(() => expect(mocks.getWidgets).toHaveBeenCalledOnce());
    mocks.auth = { loading: false, user: { id: 'user-2' } };
    view.rerender(<WidgetsPage />);
    await waitFor(() => expect(mocks.getWidgets).toHaveBeenCalledTimes(2));
    await act(async () => finishOld([{ id: 'old', name: 'Old workspace widget', workflow_id: 10 }]));
    expect(screen.queryByText('Old workspace widget')).toBeNull();
  });

  it('cannot reopen an old embed snippet after the workspace changes', async () => {
    let finishOld!: (value: unknown) => void;
    mocks.getWidgets.mockResolvedValueOnce([{ id: 'old', name: 'Pending embed', workflow_id: 10 }]).mockResolvedValue([]);
    mocks.updateWidget.mockReturnValueOnce(new Promise(resolve => { finishOld = resolve; }));
    const view = render(<WidgetsPage />);
    const row = (await screen.findByText('Pending embed')).closest('tr')!;
    fireEvent.click(within(row).getAllByRole('button')[0]);
    await waitFor(() => expect(mocks.updateWidget).toHaveBeenCalledOnce());
    mocks.auth = { loading: false, user: { id: 'user-2' } };
    view.rerender(<WidgetsPage />);
    await waitFor(() => expect(mocks.getWidgets).toHaveBeenCalledTimes(2));
    await act(async () => finishOld({ id: 'old', embed_code: '<script data-test="old-workspace"></script>' }));
    expect(screen.queryByText(/old-workspace/)).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
