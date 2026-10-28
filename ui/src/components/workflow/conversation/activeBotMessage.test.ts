import { describe, expect, it } from 'vitest';
import { activeBotMessageIndex, finalizeActiveBotMessage } from './activeBotMessage';
import type { RealtimeFeedbackMessage } from './types';

const message = (type: RealtimeFeedbackMessage['type'], final?: boolean): RealtimeFeedbackMessage => ({
    id: type,
    type,
    text: 'hello',
    final,
    timestamp: '2026-10-20T00:00:00.000Z',
});

describe('active bot preview', () => {
    it('reuses one preview despite LLM and response timing events before speech', () => {
        const messages = [message('bot-text', false), message('ttfb-metric'), message('latency-metric')];
        expect(activeBotMessageIndex(messages)).toBe(0);
    });

    it('does not merge across a caller turn or a completed bot reply', () => {
        expect(activeBotMessageIndex([message('bot-text', false), message('user-transcription')])).toBe(-1);
        expect(activeBotMessageIndex([message('bot-text', true), message('ttfb-metric')])).toBe(-1);
    });

    it('keeps generated text when the next caller turn arrives before audio confirmation', () => {
        const history = [message('bot-text', true), { ...message('bot-text', false), id: 'new', text: 'A complete generated reply' }];
        const finalized = finalizeActiveBotMessage(history, '');
        expect(finalized).toHaveLength(2);
        expect(finalized[0]).toBe(history[0]);
        expect(finalized[1]).toMatchObject({ text: 'A complete generated reply', final: true, audioStatus: 'unconfirmed' });
        expect(history[1].final).toBe(false);
    });

    it('preserves the full generated reply when only its first words were confirmed', () => {
        const finalized = finalizeActiveBotMessage([{ ...message('bot-text', false), text: 'One sentence. Another sentence.' }], 'One sentence.');
        expect(finalized[0]).toMatchObject({ text: 'One sentence. Another sentence.', audioStatus: 'partial' });
    });

    it('marks a fully confirmed reply final without an audio warning', () => {
        const finalized = finalizeActiveBotMessage([{ ...message('bot-text', false), text: 'The reply.' }], 'The   reply.');
        expect(finalized[0].final).toBe(true);
        expect(finalized[0].audioStatus).toBeUndefined();
    });
});
