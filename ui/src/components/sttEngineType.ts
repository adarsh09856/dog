export type SttEngineType = "cloud" | "local_cpu";

export type SttModelOption = { value: string };

/**
 * Resolve a saved STT selection against the models the current engine actually
 * exposes. Local inventories have a concrete installed model (not a synthetic
 * `auto` model), so a missing/obsolete saved ID must fall back to that model.
 */
export function sttModelValueForSelection(
    savedModel: string | undefined,
    models: SttModelOption[],
    isLocalCpu: boolean,
): string | undefined {
    if (savedModel && models.some((model) => model.value === savedModel)) {
        return savedModel;
    }
    if (isLocalCpu) return models[0]?.value;
    return models.find((model) => model.value === "auto")?.value
        || models[0]?.value;
}

/**
 * Return only languages the selected recognizer can actually run. The managed
 * provider language list is not the local model inventory: filtering that list
 * alone silently hides installed local recognizers such as Assamese and Bodo.
 */
export function recognitionLanguagesForSttModel(
    defaultLanguages: string[],
    installedLanguages: string[],
    isLocalCpu: boolean,
    supportsAutoDetect: boolean,
): string[] {
    if (!isLocalCpu) {
        return supportsAutoDetect
            ? defaultLanguages
            : defaultLanguages.filter((language) => language !== "multi");
    }

    const installedBases = Array.from(new Set(
        installedLanguages
            .map((language) => language.trim().toLowerCase().replace(/_/g, "-").split("-")[0])
            .filter((language) => language && language !== "multi"),
    ));
    return [
        ...(supportsAutoDetect && installedBases.length > 0 ? ["multi"] : []),
        ...installedBases,
    ];
}

/** Infer legacy configs from their selected model/provider when no engine type was saved. */
export function inferSttEngineType(
    savedEngineType: string | undefined,
    model: string | undefined,
    provider?: string,
): SttEngineType {
    if (savedEngineType === "cloud" || savedEngineType === "local_cpu") {
        return savedEngineType;
    }

    const normalizedModel = (model || "").trim().toLowerCase();
    const normalizedProvider = (provider || "").trim().toLowerCase();
    if (
        normalizedModel === "indicconformer-ctc-int8"
        || normalizedModel.startsWith("systran/faster-whisper")
        || normalizedModel.startsWith("faster-whisper")
        || normalizedModel.startsWith("faster-distil-whisper")
        || ["indicconformer", "speaches", "local_cpu"].includes(normalizedProvider)
    ) {
        return "local_cpu";
    }
    return "cloud";
}

/** Keep recognition settings within the selected local model's inventory. */
export function languageForLocalSttSelection(
    currentLanguage: string,
    supportsAutoDetect: boolean,
    installedLanguages: string[],
    preferredLanguages: string[],
    defaultLanguage: string,
): string {
    const baseCode = (language: string) => language.trim().toLowerCase().replace(/_/g, "-").split("-")[0];
    const installed = Array.from(new Set(installedLanguages.map(baseCode)
        .filter((language) => language && language !== "multi")));
    if (currentLanguage === "multi" && supportsAutoDetect && installed.length > 0) return "multi";
    const currentCode = baseCode(currentLanguage);
    if (installed.includes(currentCode)) return currentCode;
    for (const preferred of preferredLanguages) {
        const code = baseCode(preferred);
        if (code && code !== "multi" && installed.includes(code)) return code;
    }
    const defaultCode = baseCode(defaultLanguage);
    if (defaultCode && installed.includes(defaultCode)) return defaultCode;
    return installed[0] || defaultLanguage;
}
