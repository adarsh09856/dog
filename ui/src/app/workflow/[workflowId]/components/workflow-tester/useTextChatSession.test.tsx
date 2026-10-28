import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ create: vi.fn(), append: vi.fn(), get: vi.fn(), end: vi.fn(), rewind: vi.fn() }));
vi.mock('@/client/sdk.gen', () => ({
    createTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsPost: api.create,
    appendTextChatMessageApiV1WorkflowWorkflowIdTextChatSessionsRunIdMessagesPost: api.append,
    getTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsRunIdGet: api.get,
    endTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsRunIdEndPost: api.end,
    rewindTextChatSessionApiV1WorkflowWorkflowIdTextChatSessionsRunIdRewindPost: api.rewind,
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { useTextChatSession } from './useTextChatSession';

describe('failed text-chat sends', () => {
    it('refreshes the server revision, keeps the draft and never resends automatically', async () => {
        const session = { workflow_run_id: 407, revision: 2, is_completed: false,
            session_data: { turns: [], status: 'ready' }, checkpoint: {} };
        api.create.mockResolvedValue({ data: session });
        api.append.mockResolvedValueOnce({ error: { detail: 'Revision conflict' } });
        api.get.mockResolvedValue({ data: { ...session, revision: 4 } });
        const { result } = renderHook(() => useTextChatSession({ workflowId: 21, ready: true, disabled: false }));
        act(() => result.current.startSession());
        await waitFor(() => expect(result.current.session?.revision).toBe(2));
        act(() => result.current.setDraft('Can you speak English?'));
        await act(async () => result.current.submitComposer());
        expect(result.current.session?.revision).toBe(4);
        expect(result.current.draft).toBe('Can you speak English?');
        expect(api.append).toHaveBeenCalledTimes(1);
        expect(api.get).toHaveBeenCalledWith({ path: { workflow_id: 21, run_id: 407 } });
        api.append.mockResolvedValueOnce({ data: { ...session, revision: 6 } });
        await act(async () => result.current.submitComposer());
        expect(api.append.mock.calls[1][0].body.expected_revision).toBe(4);
        expect(result.current.draft).toBe('');
    });
});
