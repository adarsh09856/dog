import type { RealtimeFeedbackMessage } from './types';

/** Replace only the current interim utterance; keep earlier caller turns visible. */
export function replacePendingTranscription(
    messages: RealtimeFeedbackMessage[],
    transcription: RealtimeFeedbackMessage,
): RealtimeFeedbackMessage[] {
    for (let index = messages.length - 1; index >= 0; index--) {
        const message = messages[index];
        if (
            message.type === 'bot-text'
            || message.type === 'user-transcription' && message.final
            || message.type === 'pipeline-error'
            || message.type === 'function-call'
            || message.type === 'node-transition'
            || message.type === 'interrupt-warning'
        ) {
            break;
        }
        if (message.type === 'user-transcription') {
            // Interim frames are cumulative for this service, but provider
            // corrections can rewrite earlier words. Replace only when the
            // new hypothesis extends the existing text; otherwise retain the
            // old bubble and start a new one instead of erasing caller history.
            const previous = normalizeTranscript(message.text);
            const next = normalizeTranscript(transcription.text);
            if (!previous || !next.startsWith(previous)) {
                break;
            }
            const updated = [...messages];
            updated[index] = transcription;
            return updated;
        }
    }
    return [...messages, transcription];
}

function normalizeTranscript(text: string) {
    return text.trim().replace(/\s+/g, " ").toLocaleLowerCase();
}
