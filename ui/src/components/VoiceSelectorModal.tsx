"use client";

import { Check, ChevronDown, Loader2, Pencil, Play, Square } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getVoicesApiV1UserConfigurationsVoicesProviderGet } from "@/client/sdk.gen";
import { VoiceInfo } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ACCENT_DISPLAY_NAMES } from "@/constants/accents";
import { LANGUAGE_DISPLAY_NAMES } from "@/constants/languages";
import { cn } from "@/lib/utils";

const ALL_FILTER_VALUE = "__all__";

// Defaults to show all voices across global, Indic, and specialized providers.
const DEFAULT_GENDER = ALL_FILTER_VALUE;
const DEFAULT_ACCENT = ALL_FILTER_VALUE;
const DEFAULT_LANGUAGE = ALL_FILTER_VALUE;

const SEARCH_DEBOUNCE_MS = 300;

interface Facets {
    genders: string[];
    accents: string[];
    languages: string[];
    providers?: string[];
}

const EMPTY_FACETS: Facets = { genders: [], accents: [], languages: [], providers: [] };

const PROVIDER_TABS = [
    { id: "__all__", label: "All Active Voices" },
    { id: "speaches", label: "Local Kokoro" },
    { id: "sarvam", label: "Sarvam Indic" },
    { id: "cartesia", label: "Cartesia Sonic" },
    { id: "openai", label: "OpenAI" },
    { id: "elevenlabs", label: "ElevenLabs" },
    { id: "deepgram", label: "Deepgram Aura" },
    { id: "azure", label: "Azure Neural" },
    { id: "google", label: "Gemini / Google" },
    { id: "navana", label: "Navana Indic" },
    { id: "smallest", label: "Smallest AI" },
    { id: "lmnt", label: "LMNT" },
    { id: "rime", label: "Rime" },
];

interface VoiceSelectorModalProps {
    provider: string;
    value: string;
    onChange: (voiceId: string) => void;
    /** Optional model passed through to the voice catalog query. */
    model?: string;
    /** Allow typing a raw voice ID for voices outside the catalog. */
    allowManualInput?: boolean;
    className?: string;
}

const capitalize = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

const accentLabel = (code?: string | null) =>
    code ? ACCENT_DISPLAY_NAMES[code.toLowerCase()] || capitalize(code) : "";
const languageLabel = (code?: string | null) =>
    code ? LANGUAGE_DISPLAY_NAMES[code] || code.toUpperCase() : "";
const genderLabel = (gender?: string | null) => (gender ? capitalize(gender) : "");

/** Build the "Accent · Gender · Language" trait line shown under a voice name. */
function voiceTraits(voice: VoiceInfo): string {
    return [accentLabel(voice.accent), genderLabel(voice.gender), languageLabel(voice.language)]
        .filter(Boolean)
        .join(" · ");
}

/** Ensure the active filter value is always an option so the Select can render it. */
function withSelected(options: string[], selected: string): string[] {
    if (selected === ALL_FILTER_VALUE || options.includes(selected)) return options;
    return [selected, ...options];
}

export const VoiceSelectorModal: React.FC<VoiceSelectorModalProps> = ({
    provider,
    value,
    onChange,
    model,
    allowManualInput = false,
    className,
}) => {
    const [isOpen, setIsOpen] = useState(false);
    const [voices, setVoices] = useState<VoiceInfo[]>([]);
    const [facets, setFacets] = useState<Facets>(EMPTY_FACETS);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [providerFilter, setProviderFilter] = useState("__all__");

    const activeTabs = useMemo(() => {
        if (provider === "speaches") {
            return [{ id: "__all__", label: "Local Kokoro Voices" }];
        }
        const activeProvList = facets.providers || [];
        if (activeProvList.length === 0) {
            const detected = Array.from(new Set(voices.map((v) => (v as any).provider).filter(Boolean)));
            if (detected.length > 0) {
                return [
                    { id: "__all__", label: `All Active Voices (${voices.length})` },
                    ...PROVIDER_TABS.filter((t) => t.id !== "__all__" && detected.includes(t.id)),
                ];
            }
            return [{ id: "__all__", label: `All Voices (${voices.length || 0})` }];
        }
        return [
            { id: "__all__", label: `All Active Voices (${voices.length})` },
            ...PROVIDER_TABS.filter((t) => t.id !== "__all__" && activeProvList.includes(t.id)),
        ];
    }, [provider, facets.providers, voices]);

    useEffect(() => {
        setProviderFilter("__all__");
    }, [provider]);

    const [gender, setGender] = useState(DEFAULT_GENDER);
    const [accent, setAccent] = useState(DEFAULT_ACCENT);
    const [language, setLanguage] = useState(DEFAULT_LANGUAGE);
    const [searchInput, setSearchInput] = useState("");
    const [debouncedSearch, setDebouncedSearch] = useState("");

    // Pending (in-modal) selection; only committed via "Use this voice".
    const [pendingVoiceId, setPendingVoiceId] = useState(value);
    const [selectedVoiceInfo, setSelectedVoiceInfo] = useState<VoiceInfo | null>(null);
    const [manualMode, setManualMode] = useState(false);
    const [manualVoiceId, setManualVoiceId] = useState("");

    // Preview playback.
    const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const requestId = useRef(0);

    const stopPreview = useCallback(() => {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current = null;
        }
        setPlayingVoiceId(null);
    }, []);

    // Debounce the search box so typing doesn't fire a request per keystroke.
    useEffect(() => {
        const timer = setTimeout(() => setDebouncedSearch(searchInput), SEARCH_DEBOUNCE_MS);
        return () => clearTimeout(timer);
    }, [searchInput]);

    // Resolve the currently-selected voice (for the trigger label) without
    // pulling the catalog: a targeted lookup by voice ID.
    useEffect(() => {
        if (!value) {
            setSelectedVoiceInfo(null);
            return;
        }
        let active = true;
        (async () => {
            const response = await getVoicesApiV1UserConfigurationsVoicesProviderGet({
                path: { provider: provider as never },
                query: { q: value },
            });
            if (!active) return;
            const found = response.data?.voices?.find((voice) => voice.voice_id === value) ?? null;
            setSelectedVoiceInfo(found);
        })();
        return () => {
            active = false;
        };
    }, [value, provider]);

    // Fetch the filtered voice list (server-side) whenever the modal is open
    // and a filter changes. A request counter discards out-of-order responses.
    useEffect(() => {
        if (!isOpen || manualMode) return;
        const id = ++requestId.current;
        setIsLoading(true);
        setError(null);
        (async () => {
            const query: Record<string, string> = {};
            if (model) query.model = model;
            if (providerFilter !== "__all__") (query as any).provider_filter = providerFilter;
            if (gender !== ALL_FILTER_VALUE) query.gender = gender;
            if (accent !== ALL_FILTER_VALUE) query.accent = accent;
            if (language !== ALL_FILTER_VALUE) query.language = language;
            const search = debouncedSearch.trim();
            if (search) query.q = search;

            const response = await getVoicesApiV1UserConfigurationsVoicesProviderGet({
                path: { provider: provider as never },
                query,
            });
            if (id !== requestId.current) return; // a newer request superseded this one

            if (response.error) {
                setError("Failed to load voices");
                setVoices([]);
            } else {
                setVoices(response.data?.voices ?? []);
                if (response.data?.facets) {
                    setFacets({
                        genders: response.data.facets.genders ?? [],
                        accents: response.data.facets.accents ?? [],
                        languages: response.data.facets.languages ?? [],
                        providers: (response.data.facets as any).providers ?? [],
                    });
                }
            }
            setIsLoading(false);
        })();
    }, [isOpen, manualMode, provider, model, providerFilter, gender, accent, language, debouncedSearch]);

    // Stop any preview when the modal closes / unmounts.
    useEffect(() => {
        if (!isOpen) stopPreview();
        return () => stopPreview();
    }, [isOpen, stopPreview]);

    // Facets arrive sorted by raw code; present them sorted by display label so
    // the dropdowns read alphabetically (e.g. "American" near the top, not "us").
    const toSortedOptions = (codes: string[], selected: string, label: (code: string) => string) =>
        withSelected(codes, selected)
            .map((code) => ({ value: code, label: label(code) }))
            .sort((a, b) => a.label.localeCompare(b.label));

    const genderOptions = useMemo(
        () => toSortedOptions(facets.genders, gender, genderLabel),
        [facets.genders, gender],
    );
    const accentOptions = useMemo(
        () => toSortedOptions(facets.accents, accent, accentLabel),
        [facets.accents, accent],
    );
    const languageOptions = useMemo(
        () => toSortedOptions(facets.languages, language, languageLabel),
        [facets.languages, language],
    );

    const openModal = () => {
        setGender(DEFAULT_GENDER);
        setAccent(DEFAULT_ACCENT);
        setLanguage(DEFAULT_LANGUAGE);
        setSearchInput("");
        setDebouncedSearch("");
        setManualMode(false);
        setManualVoiceId(value);
        setPendingVoiceId(value);
        setIsOpen(true);
    };

    const playPreview = (voice: VoiceInfo) => {
        if (playingVoiceId === voice.voice_id) {
            stopPreview();
            return;
        }
        stopPreview();
        setPlayingVoiceId(voice.voice_id);

        const clear = () => {
            if (audioRef.current) audioRef.current = null;
            setPlayingVoiceId(null);
        };

        const tryWebSpeechFallback = () => {
            if (typeof window !== "undefined" && "speechSynthesis" in window) {
                try {
                    window.speechSynthesis.cancel();
                    const text = voice.language === "hi"
                        ? "नमस्ते! यह कोडवेव्स पर इस आवाज़ का पूर्वावलोकन है।"
                        : `Hello! This is a preview of the ${voice.name} voice on Kodewaves.`;
                    const utterance = new SpeechSynthesisUtterance(text);
                    if (voice.language === "hi") {
                        utterance.lang = "hi-IN";
                    } else if (voice.accent === "gb") {
                        utterance.lang = "en-GB";
                    } else if (voice.accent === "in") {
                        utterance.lang = "en-IN";
                    } else {
                        utterance.lang = "en-US";
                    }
                    utterance.onend = clear;
                    utterance.onerror = clear;
                    window.speechSynthesis.speak(utterance);
                    return;
                } catch (e) {
                    console.warn("Speech synthesis fallback failed:", e);
                }
            }
            clear();
        };

        if (!voice.preview_url) {
            tryWebSpeechFallback();
            return;
        }

        const audio = new Audio(voice.preview_url);
        audioRef.current = audio;
        audio.onended = clear;
        audio.onerror = () => {
            tryWebSpeechFallback();
        };
        audio.play().catch(() => {
            tryWebSpeechFallback();
        });
    };

    const commitSelection = () => {
        if (manualMode) {
            const next = manualVoiceId.trim();
            if (next) onChange(next);
        } else if (pendingVoiceId) {
            onChange(pendingVoiceId);
            const chosen = voices.find((voice) => voice.voice_id === pendingVoiceId);
            if (chosen) setSelectedVoiceInfo(chosen);
        }
        setIsOpen(false);
    };

    const triggerLabel = selectedVoiceInfo?.name || value || "Select a voice";
    const triggerTraits = selectedVoiceInfo ? voiceTraits(selectedVoiceInfo) : "";

    return (
        <div className={cn("space-y-2", className)}>
            <Button
                type="button"
                variant="outline"
                className={cn("w-full justify-between", !value && "text-muted-foreground")}
                onClick={openModal}
            >
                <span className="flex min-w-0 items-center gap-2">
                    <span className="truncate font-medium">{triggerLabel}</span>
                    {triggerTraits && (
                        <span className="truncate text-xs text-muted-foreground">{triggerTraits}</span>
                    )}
                </span>
                <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </Button>

            <Dialog open={isOpen} onOpenChange={setIsOpen}>
                <DialogContent className="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-3xl">
                    <DialogHeader className="border-b px-6 py-4">
                        <DialogTitle>Select Voice</DialogTitle>
                    </DialogHeader>

                    {/* Provider Filter Tabs */}
                    <div className="flex items-center gap-1.5 overflow-x-auto border-b bg-muted/20 px-6 py-2.5 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden shrink-0">
                        {activeTabs.map((tab) => (
                            <button
                                key={tab.id}
                                type="button"
                                onClick={() => setProviderFilter(tab.id)}
                                className={cn(
                                    "whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                                    providerFilter === tab.id
                                        ? "bg-primary text-primary-foreground shadow-sm"
                                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                )}
                            >
                                {tab.label}
                            </button>
                        ))}
                    </div>

                    {/* Filter row: Gender · Accent · Language · Search */}
                    <div className="flex flex-wrap items-center gap-2 border-b px-6 py-3">
                        <Select value={gender} onValueChange={setGender} disabled={manualMode}>
                            <SelectTrigger className="h-9 w-[130px]">
                                <SelectValue placeholder="Gender" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value={ALL_FILTER_VALUE}>All genders</SelectItem>
                                {genderOptions.map((option) => (
                                    <SelectItem key={option.value} value={option.value}>
                                        {option.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                        <Select value={accent} onValueChange={setAccent} disabled={manualMode}>
                            <SelectTrigger className="h-9 w-[140px]">
                                <SelectValue placeholder="Accent" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value={ALL_FILTER_VALUE}>All accents</SelectItem>
                                {accentOptions.map((option) => (
                                    <SelectItem key={option.value} value={option.value}>
                                        {option.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                        <Select value={language} onValueChange={setLanguage} disabled={manualMode}>
                            <SelectTrigger className="h-9 w-[150px]">
                                <SelectValue placeholder="Language" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value={ALL_FILTER_VALUE}>All languages</SelectItem>
                                {languageOptions.map((option) => (
                                    <SelectItem key={option.value} value={option.value}>
                                        {option.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                        <Input
                            placeholder="Search voices..."
                            value={searchInput}
                            onChange={(event) => setSearchInput(event.target.value)}
                            className="h-9 min-w-[160px] flex-1"
                            disabled={manualMode}
                        />
                    </div>

                    {/* Body */}
                    <div className="min-h-[260px] flex-1 overflow-auto px-6 py-4">
                        {manualMode ? (
                            <div className="space-y-2">
                                <Label htmlFor="manual-voice-id">Custom voice ID</Label>
                                <Input
                                    id="manual-voice-id"
                                    placeholder="Enter voice ID"
                                    value={manualVoiceId}
                                    onChange={(event) => setManualVoiceId(event.target.value)}
                                    autoFocus
                                />
                                <p className="text-xs text-muted-foreground">
                                    Use a voice ID that isn&apos;t in the catalog above.
                                </p>
                            </div>
                        ) : error ? (
                            <p className="py-10 text-center text-sm text-destructive">{error}</p>
                        ) : isLoading ? (
                            <div className="flex items-center justify-center py-10">
                                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                            </div>
                        ) : voices.length === 0 ? (
                            <p className="py-10 text-center text-sm text-muted-foreground">
                                No voices match these filters
                            </p>
                        ) : (
                            <div className="grid gap-2 sm:grid-cols-2">
                                {voices.map((voice) => {
                                    const isSelected = pendingVoiceId === voice.voice_id;
                                    const isPlaying = playingVoiceId === voice.voice_id;
                                    return (
                                        <button
                                            type="button"
                                            key={voice.voice_id}
                                            onClick={() => setPendingVoiceId(voice.voice_id)}
                                            className={cn(
                                                "flex items-center gap-3 rounded-lg border p-3 text-left transition-colors hover:bg-accent",
                                                isSelected ? "border-primary ring-1 ring-primary" : "border-border",
                                            )}
                                        >
                                            <span
                                                role="button"
                                                tabIndex={voice.preview_url ? 0 : -1}
                                                aria-label={isPlaying ? "Stop preview" : "Play preview"}
                                                onClick={(event) => {
                                                    event.stopPropagation();
                                                    playPreview(voice);
                                                }}
                                                onKeyDown={(event) => {
                                                    if (event.key === "Enter" || event.key === " ") {
                                                        event.preventDefault();
                                                        event.stopPropagation();
                                                        playPreview(voice);
                                                    }
                                                }}
                                                className={cn(
                                                    "flex h-10 w-10 shrink-0 items-center justify-center rounded-full",
                                                    voice.preview_url
                                                        ? "bg-primary/10 text-primary hover:bg-primary/20"
                                                        : "bg-muted text-muted-foreground",
                                                )}
                                            >
                                                {isPlaying ? (
                                                    <Square className="h-4 w-4 fill-current" />
                                                ) : (
                                                    <Play className="h-4 w-4 fill-current" />
                                                )}
                                            </span>
                                            <span className="flex min-w-0 flex-1 flex-col">
                                                <span className="flex items-center gap-2">
                                                    <span className="truncate text-sm font-medium">{voice.name}</span>
                                                    {((voice as any).provider) && (
                                                        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                                                            {(voice as any).provider}
                                                        </span>
                                                    )}
                                                    {isSelected && <Check className="h-4 w-4 shrink-0 text-primary" />}
                                                </span>
                                                {voiceTraits(voice) && (
                                                    <span className="truncate text-xs text-muted-foreground">
                                                        {voiceTraits(voice)}
                                                    </span>
                                                )}
                                                <span className="truncate text-[11px] text-muted-foreground/70">
                                                    ID: {voice.voice_id}
                                                </span>
                                            </span>
                                        </button>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    {/* Footer */}
                    <div className="flex items-center justify-between gap-3 border-t px-6 py-3">
                        {allowManualInput ? (
                            <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="text-muted-foreground"
                                onClick={() => setManualMode((prev) => !prev)}
                            >
                                <Pencil className="mr-2 h-4 w-4" />
                                {manualMode ? "Browse catalog" : "Custom voice ID"}
                            </Button>
                        ) : (
                            <span className="text-xs text-muted-foreground">
                                {!manualMode && !isLoading && !error ? `${voices.length} voices` : ""}
                            </span>
                        )}
                        <div className="flex items-center gap-2">
                            <Button type="button" variant="outline" onClick={() => setIsOpen(false)}>
                                Cancel
                            </Button>
                            <Button
                                type="button"
                                onClick={commitSelection}
                                disabled={manualMode ? !manualVoiceId.trim() : !pendingVoiceId}
                            >
                                Use this voice
                            </Button>
                        </div>
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    );
};
