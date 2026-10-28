import { describe, expect, it } from "vitest";
import {
    inferSttEngineType,
    languageForLocalSttSelection,
    recognitionLanguagesForSttModel,
    sttModelValueForSelection,
} from "./sttEngineType";

describe("inferSttEngineType", () => {
    it("recognizes the current local IndicConformer id when saved engine type is absent", () => {
        expect(inferSttEngineType(undefined, "indicconformer-ctc-int8")).toBe("local_cpu");
    });

    it("keeps an explicitly saved engine type authoritative", () => {
        expect(inferSttEngineType("cloud", "indicconformer-ctc-int8")).toBe("cloud");
        expect(inferSttEngineType("local_cpu", "nova-3")).toBe("local_cpu");
    });
});

describe("languageForLocalSttSelection", () => {
    it("keeps auto when the selected local recognizer advertises auto-detection", () => {
        expect(languageForLocalSttSelection("multi", true, ["hi-IN", "en-IN"], ["multi", "hi", "en"], "hi")).toBe("multi");
    });

    it("falls back to an installed language when auto-detection is unavailable", () => {
        expect(languageForLocalSttSelection("multi", false, ["hi-IN", "en-IN"], ["multi", "hi", "en"], "hi")).toBe("hi");
    });

    it("keeps an explicit language unchanged", () => {
        expect(languageForLocalSttSelection("en", false, ["hi-IN", "en-IN"], ["multi", "hi", "en"], "hi")).toBe("en");
    });

    it("replaces a removed explicit language with one the installed recognizer supports", () => {
        expect(languageForLocalSttSelection("ur", true, ["hi-IN", "en-IN"], ["multi", "hi", "en"], "hi")).toBe("hi");
        expect(languageForLocalSttSelection("hi", false, ["as-IN"], ["multi", "hi", "en"], "hi")).toBe("as");
    });

    it("reconciles a saved preference when switching to an English-only recognizer", () => {
        expect(languageForLocalSttSelection("hi", false, ["en-IN"], ["multi", "hi", "en"], "hi")).toBe("en");
    });

    it("normalizes a supported region-qualified saved language to its selector value", () => {
        expect(languageForLocalSttSelection("en-IN", true, ["hi-IN", "en-IN"], ["multi", "hi", "en"], "hi")).toBe("en");
        expect(languageForLocalSttSelection("en_IN", true, ["hi-IN", "en-IN"], ["multi", "hi", "en"], "hi")).toBe("en");
    });

    it("falls back to an installed language missing from the managed provider list", () => {
        expect(languageForLocalSttSelection("multi", false, ["as-IN"], ["multi", "hi", "en"], "hi")).toBe("as");
    });
});

describe("recognitionLanguagesForSttModel", () => {
    const managedLanguages = ["multi", "bn", "en", "en-US", "hi", "kn", "mr", "ta", "te"];
    const installedLanguages = [
        "as-IN", "bn-IN", "brx-IN", "doi-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN",
        "ks-IN", "kok-IN", "mai-IN", "ml-IN", "mni-IN", "mr-IN", "ne-IN", "or-IN",
        "pa-IN", "sa-IN", "sat-IN", "sd-IN", "ta-IN", "te-IN", "ur-IN",
    ];

    it("lists only enabled installed recognizers plus English and includes auto when supported", () => {
        expect(recognitionLanguagesForSttModel(managedLanguages, installedLanguages, true, true)).toEqual([
            "multi", "as", "bn", "brx", "doi", "en", "hi", "kn", "mai", "ml",
            "mr", "ne", "pa", "sa", "ta", "te",
        ]);
    });

    it("keeps only enabled local languages when auto-detection is unavailable", () => {
        const result = recognitionLanguagesForSttModel(managedLanguages, installedLanguages, true, false);
        expect(result).not.toContain("multi");
        expect(result).toHaveLength(15);
        expect(result).toContain("hi");
        expect(result).toContain("ta");
        for (const excluded of ["gu", "ks", "kok", "mni", "or", "sat", "sd", "ur"]) {
            expect(result).not.toContain(excluded);
        }
    });

    it("preserves the cloud provider language options", () => {
        expect(recognitionLanguagesForSttModel(managedLanguages, ["as-IN"], false, true)).toEqual(managedLanguages);
    });

    it("uses the same locale normalization for reconciliation, selector values, and save validation", () => {
        const installed = ["en_IN", "hi-IN"];
        const selection = languageForLocalSttSelection("en-IN", true, installed, managedLanguages, "hi");
        const options = recognitionLanguagesForSttModel(managedLanguages, installed, true, true);
        expect(options).toEqual(["multi", "en", "hi"]);
        expect(options).toContain(selection);
    });

    it("does not advertise an explicit fallback or auto with an empty local inventory", () => {
        const options = recognitionLanguagesForSttModel(managedLanguages, [], true, true);
        const selection = languageForLocalSttSelection("hi", false, [], managedLanguages, "hi");
        expect(options).toEqual([]);
        expect(options).not.toContain(selection);
        expect(languageForLocalSttSelection("multi", true, [], managedLanguages, "hi")).not.toBe("multi");
    });

    it("does not restore excluded saved languages when reconciling an installed local model", () => {
        const selected = languageForLocalSttSelection("ur", true, installedLanguages, managedLanguages, "hi");
        expect(selected).toBe("hi");
        expect(recognitionLanguagesForSttModel(managedLanguages, installedLanguages, true, true))
            .not.toContain(selected === "ur" ? "ur" : "gu");
    });
});

describe("sttModelValueForSelection", () => {
    const localModels = [
        { value: "indicconformer-ctc-int8" },
    ];
    const cloudModels = [
        { value: "auto" },
        { value: "nova-3" },
    ];

    it("uses the installed local model when a saved ID is missing", () => {
        expect(sttModelValueForSelection(undefined, localModels, true))
            .toBe("indicconformer-ctc-int8");
    });

    it("repairs an obsolete local model ID to the installed model", () => {
        expect(sttModelValueForSelection("faster-whisper-large-v3", localModels, true))
            .toBe("indicconformer-ctc-int8");
    });

    it("preserves an installed model selection", () => {
        expect(sttModelValueForSelection("nova-3", cloudModels, false)).toBe("nova-3");
    });

    it("prefers the cloud auto option when no model is saved", () => {
        expect(sttModelValueForSelection(undefined, cloudModels, false)).toBe("auto");
    });
});
