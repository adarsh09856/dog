"use client";

import { Brain } from "lucide-react";

import { cn } from "@/lib/utils";

interface MessageBubbleProps {
    role: "user" | "assistant";
    text: string;
    final?: boolean;
    audioStatus?: "unconfirmed" | "partial";
    tone?: "default" | "muted";
    reasoningDurationMs?: number;
    responseLatencyMs?: number;
    containerClassName?: string;
}

export function MessageBubble({
    role,
    text,
    final = true,
    audioStatus,
    tone = "default",
    reasoningDurationMs,
    responseLatencyMs,
    containerClassName,
}: MessageBubbleProps) {
    const isUser = role === "user";
    const isMuted = tone === "muted";

    return (
        <div className={cn("flex", isUser ? "justify-end" : "justify-start", containerClassName)}>
            <div className="flex max-w-[85%] flex-col gap-1">
                {!isUser && (reasoningDurationMs !== undefined || responseLatencyMs !== undefined) ? (
                    <div className="flex items-center gap-1.5 px-1 text-xs text-muted-foreground">
                        <Brain className="h-3 w-3" />
                        {responseLatencyMs !== undefined ? <><span className="font-medium">Response delay:</span><span>{Math.round(responseLatencyMs)}ms</span></> : null}
                        {reasoningDurationMs !== undefined ? <><span className="font-medium">LLM first token:</span><span>{Math.round(reasoningDurationMs)}ms</span></> : null}
                    </div>
                ) : null}
                <div
                    className={cn(
                        "whitespace-pre-wrap break-words rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm",
                        isUser
                            ? "rounded-br-md bg-primary text-primary-foreground"
                            : isMuted
                                ? "rounded-bl-md border border-dashed border-border bg-background text-muted-foreground"
                                : "rounded-bl-md border border-slate-200/80 bg-muted text-foreground",
                        !final && "opacity-70",
                    )}
                >
                    <div>{text}</div>
                    {!final ? (
                        <div
                            className={cn(
                                "mt-1 text-[10px] italic",
                                isUser ? "text-primary-foreground/70" : "text-muted-foreground",
                            )}
                        >
                            speaking...
                        </div>
                    ) : null}
                    {!isUser && final && audioStatus ? (
                        <div className="mt-1 text-[10px] italic text-muted-foreground">
                            {audioStatus === "unconfirmed" ? "Audio not confirmed" : "Audio partly confirmed"}
                        </div>
                    ) : null}
                </div>
            </div>
        </div>
    );
}
