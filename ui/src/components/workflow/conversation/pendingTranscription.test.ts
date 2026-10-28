import { describe, expect, it } from "vitest";

import type { RealtimeFeedbackMessage } from "./types";
import { replacePendingTranscription } from "./pendingTranscription";

const userMessage = (
    id: string,
    text: string,
    options: Partial<RealtimeFeedbackMessage> = {},
): RealtimeFeedbackMessage => ({
    id,
    type: "user-transcription",
    text,
    final: false,
    timestamp: "2026-10-28T10:00:00.000Z",
    ...options,
});

describe("replacePendingTranscription", () => {
    it("updates interim hypotheses from the same STT utterance", () => {
        const first = userMessage("u1", "I need help");
        const next = userMessage("u2", "I need help booking");

        const updated = replacePendingTranscription([first], next);

        expect(updated).toHaveLength(1);
        expect(updated[0]).toMatchObject({ id: "u2", text: "I need help booking" });
    });

    it("keeps an earlier unfinished utterance when STT starts a new segment", () => {
        const first = userMessage("u1", "I need help");
        const next = userMessage("u2", "Book a room");

        const updated = replacePendingTranscription([first], next);

        expect(updated).toHaveLength(2);
        expect(updated.map(({ text }) => text)).toEqual(["I need help", "Book a room"]);
    });

    it("does not replace a prior interim across a completed caller turn", () => {
        const previous = userMessage("u1", "Earlier words");
        const final = userMessage("u2", "A completed turn", { final: true });
        const next = userMessage("u3", "Next turn");

        const updated = replacePendingTranscription([previous, final], next);

        expect(updated).toHaveLength(3);
        expect(updated[0]).toBe(previous);
        expect(updated[1]).toBe(final);
        expect(updated[2]).toBe(next);
    });

    it("keeps prior caller text when a pipeline error separates two utterances", () => {
        const previous = userMessage("u1", "I need help");
        const error: RealtimeFeedbackMessage = {
            id: "error-1",
            type: "pipeline-error",
            text: "Recognition failed",
            timestamp: "2026-10-28T10:00:01.000Z",
        };
        const next = userMessage("u2", "Book a room");

        const updated = replacePendingTranscription([previous, error], next);

        expect(updated).toHaveLength(3);
        expect(updated.map(({ text }) => text)).toEqual([
            "I need help",
            "Recognition failed",
            "Book a room",
        ]);
    });
});
