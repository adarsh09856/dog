import { describe, expect, it } from 'vitest';
import { activeBotMessageIndex } from './activeBotMessage';
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
});
