import { describe, expect, it } from "vitest";
import { inferSttEngineType, languageForLocalSttSelection, recognitionLanguagesForSttModel, sttModelValueForSelection } from "./sttEngineType";

describe("inferSttEngineType", () => {
    it("recognizes local IndicConformer when saved engine type is absent", () => {
        expect(inferSttEngineType(undefined, "indicconformer-ctc-int8")).toBe("local_cpu");
    });
    it("keeps explicit engine type authoritative", () => {
        expect(inferSttEngineType("cloud", "indicconformer-ctc-int8")).toBe("cloud");
        expect(inferSttEngineType("local_cpu", "nova-3")).toBe("local_cpu");
    });
});

describe("languageForLocalSttSelection", () => {
    it("keeps auto only when the selected local recognizer supports detection", () => {
        expect(languageForLocalSttSelection("multi", true, ["hi-IN", "en-IN"], ["multi", "hi", "en"], "hi")).toBe("multi");
    });
    it("falls back to an installed language when auto is unavailable", () => {
        expect(languageForLocalSttSelection("multi", false, ["hi-IN", "en-IN"], ["multi", "hi", "en"], "hi")).toBe("hi");
    });
    it("keeps explicit language and repairs removed selections", () => {
        expect(languageForLocalSttSelection("en", false, ["hi-IN", "en-IN"], ["multi", "hi", "en"], "hi")).toBe("en");
        expect(languageForLocalSttSelection("ur", true, ["hi-IN", "en-IN"], ["multi", "hi", "en"], "hi")).toBe("hi");
        expect(languageForLocalSttSelection("hi", false, ["as-IN"], ["multi", "hi", "en"], "hi")).toBe("as");
    });
    it("reconciles language when the installed model changes", () => {
        expect(languageForLocalSttSelection("hi", false, ["en-IN"], ["multi", "hi", "en"], "hi")).toBe("en");
        expect(languageForLocalSttSelection("multi", false, ["as-IN"], ["multi", "hi", "en"], "hi")).toBe("as");
    });
    it("normalizes locale-qualified language codes", () => {
        expect(languageForLocalSttSelection("en-IN", true, ["hi-IN", "en-IN"], ["multi", "hi", "en"], "hi")).toBe("en");
        expect(languageForLocalSttSelection("en_IN", true, ["hi-IN", "en-IN"], ["multi", "hi", "en"], "hi")).toBe("en");
    });
    it("does not retain auto when local inventory is empty", () => {
        expect(languageForLocalSttSelection("multi", true, [], ["multi", "hi", "en"], "hi")).not.toBe("multi");
    });
});

describe("recognitionLanguagesForSttModel", () => {
    const managed = ["multi", "bn", "en", "en-US", "hi", "kn", "mr", "ta", "te"];
    const installed = ["as-IN", "bn-IN", "brx-IN", "doi-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ks-IN", "kok-IN", "mai-IN", "ml-IN", "mni-IN", "mr-IN", "ne-IN", "or-IN", "pa-IN", "sa-IN", "sat-IN", "sd-IN", "ta-IN", "te-IN", "ur-IN"];
    it("lists installed supported languages and auto only when available", () => {
        expect(recognitionLanguagesForSttModel(managed, installed, true, true)).toEqual(["multi", "as", "bn", "brx", "doi", "en", "hi", "kn", "mai", "ml", "mr", "ne", "pa", "sa", "ta", "te"]);
    });
    it("omits auto when unsupported and excludes disabled languages", () => {
        const options = recognitionLanguagesForSttModel(managed, installed, true, false);
        expect(options).toHaveLength(15);
        expect(options).not.toContain("multi");
        for (const code of ["gu", "ks", "kok", "mni", "or", "sat", "sd", "ur"]) expect(options).not.toContain(code);
    });
    it("preserves cloud language options", () => {
        expect(recognitionLanguagesForSttModel(managed, ["as-IN"], false, true)).toEqual(managed);
    });
    it("uses normalized locale consistently for selector and saved value", () => {
        const inventory = ["en_IN", "hi-IN"];
        const selected = languageForLocalSttSelection("en-IN", true, inventory, managed, "hi");
        const options = recognitionLanguagesForSttModel(managed, inventory, true, true);
        expect(options).toEqual(["multi", "en", "hi"]);
        expect(options).toContain(selected);
    });
    it("shows no local options if inventory is empty", () => {
        expect(recognitionLanguagesForSttModel(managed, [], true, true)).toEqual([]);
    });
});

describe("sttModelValueForSelection", () => {
    const local = [{ value: "indicconformer-ctc-int8" }];
    const cloud = [{ value: "auto" }, { value: "nova-3" }];
    it("uses installed local model when saved ID is missing", () => {
        expect(sttModelValueForSelection(undefined, local, true)).toBe("indicconformer-ctc-int8");
    });
    it("repairs obsolete local model ID", () => {
        expect(sttModelValueForSelection("faster-whisper-large-v3", local, true)).toBe("indicconformer-ctc-int8");
    });
    it("preserves installed cloud model and defaults to cloud auto", () => {
        expect(sttModelValueForSelection("nova-3", cloud, false)).toBe("nova-3");
        expect(sttModelValueForSelection(undefined, cloud, false)).toBe("auto");
    });
});
