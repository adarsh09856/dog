import { describe, expect, it } from "vitest";

import { INDIAN_TEMPLATE_LANGUAGES, WORKFLOW_GENERATION_LANGUAGES } from "./languages";

describe("language inventories", () => {
    it("keeps custom prompt generation aligned with every backend-supported speech language", () => {
        const codes = WORKFLOW_GENERATION_LANGUAGES.map(({ code }) => code);

        expect(codes).toHaveLength(38);
        expect(new Set(codes).size).toBe(codes.length);
        expect(codes).toEqual(expect.arrayContaining([
            "ar", "as", "bn", "brx", "de", "doi", "en", "es", "fr", "gu", "hi", "id",
            "it", "ja", "kn", "kok", "ko", "ks", "mai", "ml", "mni", "mr", "ne", "nl",
            "or", "pa", "pt", "ru", "sa", "sat", "sd", "ta", "te", "th", "tr", "ur",
            "vi", "zh",
        ]));
        expect(WORKFLOW_GENERATION_LANGUAGES.every(({ name }) => name.trim().length > 0)).toBe(true);
        expect(WORKFLOW_GENERATION_LANGUAGES.map(({ name }) => name)).toEqual(
            [...WORKFLOW_GENERATION_LANGUAGES.map(({ name }) => name)].sort((left, right) => left.localeCompare(right)),
        );
    });

    it("keeps localized agent templates limited to the 22 languages they actually define", () => {
        expect(INDIAN_TEMPLATE_LANGUAGES).toHaveLength(22);
    });
});
