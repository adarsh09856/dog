import { describe, expect, it } from "vitest";

import { getCategoryConfig } from "./config";

describe("unsupported tool categories", () => {
    it("explains that native tools are unavailable and lists supported alternatives", () => {
        const native = getCategoryConfig("native");

        expect(native?.disabled).toBe(true);
        expect(native?.label).toContain("Not Available");
        expect(native?.description).toContain("not available in this release");
        expect(native?.description).toContain("Transfer To Agent");
    });

    it("directs users to supported HTTP API and MCP connections", () => {
        const integration = getCategoryConfig("integration");

        expect(integration?.disabled).toBe(true);
        expect(integration?.label).toContain("Not Available");
        expect(integration?.description).toContain("not available in this release");
        expect(integration?.description).toContain("External HTTP API");
        expect(integration?.description).toContain("MCP Server");
    });
});
