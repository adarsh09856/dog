import type { RealtimeFeedbackMessage } from './types';

/** Replace only the current interim utterance; keep earlier caller turns visible. */
export function replacePendingTranscription(
    messages: RealtimeFeedbackMessage[],
    transcription: RealtimeFeedbackMessage,
): RealtimeFeedbackMessage[] {
    for (let index = messages.length - 1; index >= 0; index--) {
        const message = messages[index];
        if (message.type === 'bot-text' || message.type === 'user-transcription' && message.final) {
            break;
        }
        if (message.type === 'user-transcription') {
            const updated = [...messages];
            updated[index] = transcription;
            return updated;
        }
    }
    return [...messages, transcription];
}
