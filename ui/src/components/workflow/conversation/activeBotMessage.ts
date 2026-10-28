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

export function finalizeActiveBotMessage(
    messages: RealtimeFeedbackMessage[], spokenText: string,
): RealtimeFeedbackMessage[] {
    const index = activeBotMessageIndex(messages);
    if (index < 0) return messages;
    const message = messages[index];
    const normalized = (text: string) => text.replace(/\s+/g, ' ').trim();
    const spoken = normalized(spokenText);
    // Generated text remains useful when audio fails or the caller interrupts.
    // Keep it visibly distinct from audio-confirmed text instead of deleting it.
    const text = spoken.length > normalized(message.text).length ? spokenText : message.text;
    const audioStatus = !spoken ? 'unconfirmed' : normalized(text) === spoken ? undefined : 'partial';
    const updated = [...messages];
    updated[index] = { ...message, text, final: true, audioStatus };
    return updated;
}
