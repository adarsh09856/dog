export type SttEngineType = "cloud" | "local_cpu";

export type SttModelOption = { value: string };

// Include the complete IndicConformer decoder catalog. The selected TTS
// inventory narrows this to languages the active reply voice can actually use.
const LOCAL_STT_LANGUAGES = new Set([
    "as", "bn", "brx", "doi", "en", "gu", "hi", "kn", "ks", "kok",
    "mai", "ml", "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd",
    "ta", "te", "ur",
]);

const baseLanguageCode = (language: string) =>
    language.trim().toLowerCase().replace(/_/g, "-").split("-")[0];

const normalizedLanguageCodes = (languages: string[] | undefined) =>
    Array.from(new Set((languages ?? []).map(baseLanguageCode).filter(Boolean)));

/** Mirror only TTS adapters that can change language for each caller turn. */
export function supportsPerTurnTtsLanguageRouting(
    provider: string | undefined,
    model: string | undefined,
): boolean {
    const providerCode = (provider ?? "").trim().toLowerCase();
    const modelCode = (model ?? "").trim().toLowerCase();
    return (providerCode === "sarvam" && modelCode === "bulbul:v3")
        || (providerCode === "speaches" && ["indic-vits-rasa-13", "indic-mio-tts"].includes(modelCode));
}

/**
 * Return the configured voice's truthful reply inventory. Automatic routers
 * use their installed model inventory; fixed providers use the selected
 * voice's own language metadata instead of the broader model catalog.
 */
export function replyLanguagesForTtsSelection(
    provider: string | undefined,
    model: string | undefined,
    modelLanguages: string[] | undefined,
    voiceLanguages: string[] | undefined,
): string[] {
    const providerCode = (provider ?? "").trim().toLowerCase();
    const modelCode = (model ?? "").trim().toLowerCase();
    const modelCodes = normalizedLanguageCodes(modelLanguages);
    const voiceCodes = normalizedLanguageCodes(voiceLanguages);

    if (!supportsPerTurnTtsLanguageRouting(providerCode, modelCode)) {
        // Keep the current model's language choices visible while the
        // selected voice lookup is pending; the resolved voice inventory
        // replaces this fallback as soon as it arrives.
        return voiceLanguages === undefined ? modelCodes : voiceCodes;
    }
    // Rasa routes among its installed voices and Sarvam Bulbul v3 changes the
    // language setting while preserving its verified speaker. MIO may expose
    // per-voice metadata, which the runtime honors when present.
    if (providerCode === "speaches" && modelCode === "indic-mio-tts" && voiceCodes.length > 0) {
        return voiceCodes;
    }
    return modelCodes;
}

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
    replyLanguages?: string[],
    supportsPerTurnTtsRouting = false,
): string[] {
    const defaultBases = new Set(defaultLanguages
        .filter((language) => language !== "multi")
        .map(baseLanguageCode));
    const installedBases = Array.from(new Set(
        installedLanguages
            .map(baseLanguageCode)
            .filter((language) => defaultBases.has(language)
                && (!isLocalCpu || LOCAL_STT_LANGUAGES.has(language))),
    ));
    const replyBases = new Set((replyLanguages ?? [])
        .map(baseLanguageCode)
        .filter((language) => !isLocalCpu || LOCAL_STT_LANGUAGES.has(language)));
    const routedBases = installedBases.filter((language) => replyBases.has(language));
    return [
        ...(supportsAutoDetect && supportsPerTurnTtsRouting && routedBases.length > 0 ? ["multi"] : []),
        ...routedBases,
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
    replyLanguages?: string[],
): string {
    let installed = Array.from(new Set(installedLanguages.map(baseLanguageCode)
        .filter((language) => LOCAL_STT_LANGUAGES.has(language))));
    const replyBases = replyLanguages !== undefined
        ? new Set(replyLanguages.map(baseLanguageCode))
        : new Set(installed);
    installed = installed.filter((language) => replyBases.has(language));
    if (currentLanguage === "multi" && supportsAutoDetect && installed.length > 0) return "multi";
    const currentCode = baseLanguageCode(currentLanguage);
    if (installed.includes(currentCode)) return currentCode;
    const defaultCode = baseLanguageCode(defaultLanguage);
    if (defaultCode && installed.includes(defaultCode)) return defaultCode;
    for (const preferred of preferredLanguages) {
        const code = baseLanguageCode(preferred);
        if (code && code !== "multi" && installed.includes(code)) return code;
    }
    return installed[0] || (replyLanguages === undefined ? defaultLanguage : "");
}
