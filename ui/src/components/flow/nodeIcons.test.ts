import { Activity, Circle, ClipboardCheck, CreditCard, Globe, Headset, Link2, OctagonX, Play, Webhook } from "lucide-react";
import { describe, expect, it } from "vitest";

import { resolveNodeIcon } from "./nodeIcons";

describe("resolveNodeIcon", () => {
    it.each([
        ["Activity", Activity],
        ["ClipboardCheck", ClipboardCheck],
        ["CreditCard", CreditCard],
        ["Globe", Globe],
        ["Headset", Headset],
        ["Link2", Link2],
        ["OctagonX", OctagonX],
        ["Play", Play],
        ["Webhook", Webhook],
    ])("resolves the built-in %s node icon", (name, icon) => {
        expect(resolveNodeIcon(name)).toBe(icon);
    });

    it("falls back for unknown extension icons", () => {
        expect(resolveNodeIcon("UnregisteredExtensionIcon")).toBe(Circle);
    });
});
