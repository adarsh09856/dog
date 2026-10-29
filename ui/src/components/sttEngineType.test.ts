import { describe, expect, it } from "vitest";
import { inferSttEngineType, recognitionLanguagesForSttModel } from "./sttEngineType";

describe("inferSttEngineType", () => {
    it("recognizes the current local IndicConformer id when saved engine type is absent", () => {
        expect(inferSttEngineType(undefined, "indicconformer-ctc-int8")).toBe("local_cpu");
    });
    it("keeps an explicitly saved engine type authoritative", () => {
        expect(inferSttEngineType("cloud", "indicconformer-ctc-int8")).toBe("cloud");
        expect(inferSttEngineType("local_cpu", "nova-3")).toBe("local_cpu");
    });
});

describe("recognitionLanguagesForSttModel", () => {
    const managed = ["multi", "bn", "en", "hi", "kn", "mr", "ta", "te"];
    const installed = ["as-IN", "bn-IN", "brx-IN", "doi-IN", "en-IN", "hi-IN", "kn-IN", "mai-IN", "ml-IN", "mr-IN", "ne-IN", "pa-IN", "sa-IN", "ta-IN", "te-IN"];
    it("shows all installed local languages and auto-detect when supported", () => {
        expect(recognitionLanguagesForSttModel(managed, installed, true, true)).toEqual(["multi", "as", "bn", "brx", "doi", "en", "hi", "kn", "mai", "ml", "mr", "ne", "pa", "sa", "ta", "te"]);
    });
    it("does not advertise auto-detect when the local engine cannot do it", () => {
        const languages = recognitionLanguagesForSttModel(managed, installed, true, false);
        expect(languages).toHaveLength(15);
        expect(languages).not.toContain("multi");
    });
    it("keeps cloud choices unchanged", () => {
        expect(recognitionLanguagesForSttModel(managed, installed, false, true)).toEqual(managed);
    });
});
