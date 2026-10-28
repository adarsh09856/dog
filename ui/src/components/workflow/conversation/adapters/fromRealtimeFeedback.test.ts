import { describe, expect, it } from "vitest";

import type { RealtimeFeedbackEvent, TtfbKind } from "../types";
import { conversationItemsFromLiveFeedback, conversationItemsFromRealtimeFeedbackEvents, isLlmTtfb } from "./fromRealtimeFeedback";

const timestamp = "2026-09-23T10:00:00.000Z";

function ttfbEvent(seconds: number, kind?: TtfbKind): RealtimeFeedbackEvent {
    return {
        type: "rtf-ttfb-metric",
        payload: { ttfb_seconds: seconds, ...(kind ? { kind } : {}) },
        timestamp,
        turn: 1,
    };
}

describe("reasoning delay", () => {
    it("uses the LLM TTFB in stored runs, not the STT or TTS one around it", () => {
        const items = conversationItemsFromRealtimeFeedbackEvents([
            ttfbEvent(0.3, "stt"),
            ttfbEvent(0.8, "llm"),
            ttfbEvent(0.2, "tts"),
            { type: "rtf-bot-text", payload: { text: "Hello" }, timestamp, turn: 1 },
        ]);

        expect(items[0]).toMatchObject({ role: "assistant", reasoningDurationMs: 800 });
    });

    it("reads TTFB without a kind as the LLM's", () => {
        const items = conversationItemsFromRealtimeFeedbackEvents([
            ttfbEvent(0.8),
            { type: "rtf-bot-text", payload: { text: "Hello" }, timestamp, turn: 1 },
        ]);

        expect(items[0]).toMatchObject({ reasoningDurationMs: 800 });
    });

    it("keeps the measured response delay separate from the LLM first token", () => {
        const events: RealtimeFeedbackEvent[] = [
            ttfbEvent(0.3, "llm"),
            { type: "rtf-latency-measured", payload: { latency_seconds: 4.2 }, timestamp, turn: 1 },
            { type: "rtf-bot-text", payload: { text: "Hello" }, timestamp, turn: 1 },
        ];
        expect(conversationItemsFromRealtimeFeedbackEvents(events)[0]).toMatchObject({
            reasoningDurationMs: 300,
            responseLatencyMs: 4200,
        });
        expect(conversationItemsFromLiveFeedback([
            { id: "llm", type: "ttfb-metric", text: "300ms", ttfbSeconds: 0.3, timestamp },
            { id: "response", type: "latency-metric", text: "4200ms", latencySeconds: 4.2, timestamp },
            { id: "bot", type: "bot-text", text: "Hello", timestamp },
        ])[0]).toMatchObject({ reasoningDurationMs: 300, responseLatencyMs: 4200 });
    });

    // The live hook drops non-LLM TTFB with this before it reaches state.
    it("counts only LLM TTFB, and untagged TTFB as LLM", () => {
        expect(isLlmTtfb("llm")).toBe(true);
        expect(isLlmTtfb(undefined)).toBe(true);
        expect(isLlmTtfb("stt")).toBe(false);
        expect(isLlmTtfb("tts")).toBe(false);
    });
});
