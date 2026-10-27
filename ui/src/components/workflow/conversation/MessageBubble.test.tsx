import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MessageBubble } from "./MessageBubble";

describe("MessageBubble theme surfaces", () => {
    it("uses shared theme tokens for assistant and user bubbles", () => {
        render(
            <>
                <MessageBubble role="assistant" text="Hello" />
                <MessageBubble role="user" text="Hi" />
            </>,
        );

        const assistant = screen.getByText("Hello").parentElement;
        const user = screen.getByText("Hi").parentElement;

        expect(assistant?.className).toContain("border-border");
        expect(assistant?.className).toContain("bg-muted");
        expect(assistant?.className).toContain("text-foreground");
        expect(user?.className).toContain("bg-primary");
        expect(user?.className).toContain("text-primary-foreground");
    });

    it("uses the background and border tokens for a muted assistant bubble", () => {
        render(<MessageBubble role="assistant" text="Speaking" final={false} tone="muted" />);

        const bubble = screen.getByText("Speaking").parentElement;
        expect(bubble?.className).toContain("border-border");
        expect(bubble?.className).toContain("bg-background");
        expect(bubble?.className).toContain("text-muted-foreground");
        expect(screen.getByText("speaking...")).toBeTruthy();
    });
});
