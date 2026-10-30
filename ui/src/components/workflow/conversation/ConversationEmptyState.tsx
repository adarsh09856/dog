"use client";

import { MessageSquare } from "lucide-react";

import type { ConversationEmptyStateData } from "./types";

export function ConversationEmptyState({ title, subtitle }: ConversationEmptyStateData) {
    return (
        <div className="flex h-full flex-col items-center justify-center text-sm text-muted-foreground">
            <MessageSquare className="mb-5 h-9 w-9 text-primary opacity-60" />
            <p className="text-base font-medium tracking-tight text-foreground">{title}</p>
            <p className="mt-1 px-4 text-center text-xs">{subtitle}</p>
        </div>
    );
}
