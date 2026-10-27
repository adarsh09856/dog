import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { buildLucideModularizeImports } from "./lucide-modularize-imports";

describe("buildLucideModularizeImports", () => {
    it("maps every UI value import to its direct icon module", () => {
        const rootIndex = readFileSync(
            require.resolve("lucide-react/dist/esm/lucide-react.js"),
            "utf8",
        );
        const mapping = buildLucideModularizeImports(
            [
                path.resolve(process.cwd(), "src"),
                path.resolve(process.cwd(), "node_modules/@stackframe/stack/dist/esm"),
                path.resolve(process.cwd(), "node_modules/@stackframe/stack-ui/dist/esm"),
            ],
            rootIndex,
        );

        expect(mapping.Activity).toBe("lucide-react/dist/esm/icons/activity.js");
        expect(mapping.Trash2Icon).toBe("lucide-react/dist/esm/icons/trash-2.js");
        expect(mapping.EyeIcon).toBe("lucide-react/dist/esm/icons/eye.js");
        expect(Object.keys(mapping).length).toBeGreaterThan(100);
    });

    it("rejects namespace imports that pull in the full icon library", () => {
        const rootIndex = `export { default as Activity } from "./icons/activity.js";`;
        const sourceDirectory = mkdtempSync(path.join(os.tmpdir(), "kodewaves-lucide-"));
        try {
            writeFileSync(
                path.join(sourceDirectory, "node.tsx"),
                'import * as Icons from "lucide-react"; export const count = Object.keys(Icons).length;',
            );
            expect(() => buildLucideModularizeImports([sourceDirectory], rootIndex)).toThrow(
                "Lucide namespace import loads the full icon barrel",
            );
        } finally {
            const tempRoot = path.resolve(os.tmpdir());
            const resolvedFixture = path.resolve(sourceDirectory);
            if (!resolvedFixture.startsWith(`${tempRoot}${path.sep}`)) {
                throw new Error(`Refusing to remove fixture outside temp: ${resolvedFixture}`);
            }
            rmSync(resolvedFixture, { recursive: true, force: true });
        }
    });
});
