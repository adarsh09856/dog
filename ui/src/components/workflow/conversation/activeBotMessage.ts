import type { RealtimeFeedbackMessage } from './types';

export function activeBotMessageIndex(messages: RealtimeFeedbackMessage[]): number {
    for (let index = messages.length - 1; index >= 0; index--) {
        const message = messages[index];
        if (message.type === 'bot-text') return message.final ? -1 : index;
        if (message.type === 'user-transcription' || message.type === 'function-call' || message.type === 'node-transition') return -1;
        // Timing metrics can arrive between preview tokens and spoken text.
    }
    return -1;
}
