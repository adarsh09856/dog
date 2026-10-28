/** Keep a selected single-language local voice compatible with installed STT. */
export function recognitionLanguageForLocalVoice(
    current: string,
    voice: { languages?: string[] | null; language?: string | null } | undefined,
    installedLanguages: string[],
): string {
    if (!voice || ["multi", "auto", "caller", "default"].includes(current.toLowerCase())) return current;
    const base = (value: string) => value.toLowerCase().replace(/_/g, "-").split("-")[0];
    const languages = [...new Set((voice.languages?.length ? voice.languages : [voice.language ?? ""])
        .filter(Boolean).map(base))];
    if (languages.length !== 1 || languages[0] === "multi" || languages[0] === base(current)) return current;
    // An explicit regional voice choice can change a pinned recognizer's
    // language, but cannot enable a language absent from its installed list.
    return installedLanguages.find(language => base(language) === languages[0]) ?? current;
}
