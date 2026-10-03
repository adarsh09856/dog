"use client";

import { Bot, CheckCircle2, Cloud, Cpu, Info, Mic, Save, ShieldCheck, Sparkles, Volume2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type {
    ModelConfigurationMetricPrice,
    ModelConfigurationPricingResponse,
    OrganizationAiModelConfigurationV2,
} from "@/client/types.gen";
import {
    type ProviderSchema,
    type ServiceConfigurationDefaults,
    ServiceConfigurationForm,
    type ServiceSegment,
} from "@/components/ServiceConfigurationForm";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { VoiceSelectorModal } from "@/components/VoiceSelectorModal";
import { LANGUAGE_DISPLAY_NAMES } from "@/constants/languages";
import { formatRoundingPolicy } from "@/lib/billingDisplay";
import { catalogApi, type AvailableCatalogResponse } from "@/lib/kodewavesApi";

type ModelMode = "realtime" | "kodewaves" | "dograh" | "byok";

// Sentinel language value for "Multilingual (Auto-detect)".
const MULTILINGUAL_LANGUAGE_CODE = "multi";

export interface KodewavesDefaults {
    voices: string[];
    allow_custom_input?: boolean;
    speeds: number[];
    speed_range?: {
        min: number;
        max: number;
        step?: number;
    };
    languages: string[];
    // Languages covered by the "multi" (Multilingual / Auto-detect) option.
    multilingual_languages?: string[];
    defaults: {
        voice: string;
        speed: number;
        language: string;
    };
}
export type DograhDefaults = KodewavesDefaults;

export interface ModelConfigurationDefaultsV2 {
    kodewaves?: KodewavesDefaults;
    dograh: DograhDefaults;
    byok: {
        pipeline: ServiceConfigurationDefaults;
        realtime: {
            realtime: Record<string, ProviderSchema>;
            llm: Record<string, ProviderSchema>;
            embeddings: Record<string, ProviderSchema>;
            default_providers: ServiceConfigurationDefaults["default_providers"];
        };
    };
}

export interface KodewavesFormState {
    api_key: string;
    voice: string;
    speed: number;
    language: string;
    engine_type?: "cloud" | "local_cpu";
    llm_engine_type?: "cloud" | "local_cpu";
    stt_engine_type?: "cloud" | "local_cpu";
    tts_engine_type?: "cloud" | "local_cpu";
    llm_model?: string;
    stt_model?: string;
    tts_model?: string;
}
export type DograhFormState = KodewavesFormState;

export const CLOUD_LLM_MODELS = [
    { value: "auto", label: "Auto (Recommended - Best master key)" },
    { value: "gemini-2.5-flash", label: "Google Gemini 2.5 Flash (Ultra Fast)" },
    { value: "gemini-2.5-pro", label: "Google Gemini 2.5 Pro (Deep Reasoning)" },
    { value: "gpt-4o-mini", label: "OpenAI GPT-4o Mini (Fast & Cost-effective)" },
    { value: "gpt-4o", label: "OpenAI GPT-4o (High Intelligence)" },
    { value: "claude-3-5-sonnet-latest", label: "Anthropic Claude 3.5 Sonnet (Advanced)" },
    { value: "llama-3.3-70b-versatile", label: "Groq Llama 3.3 70B (Ultra Low Latency)" },
    { value: "sarvam-2b", label: "Sarvam Indic 2B (Indian Languages)" },
];

export const LOCAL_LLM_MODELS = [
    { value: "qwen2.5:1.5b", label: "Qwen 2.5 1.5B (Recommended CPU, ~980MB RAM)" },
    { value: "qwen2.5:0.5b", label: "Qwen 2.5 0.5B (Ultra-fast CPU, ~350MB RAM)" },
];

export const CLOUD_STT_MODELS = [
    { value: "auto", label: "Auto (Recommended - Best matched for language)" },
    { value: "gemini-stt", label: "Google Gemini Multimodal STT (Speech-to-Text)" },
    { value: "deepgram-nova-3", label: "Deepgram Nova-3 (Highest Accuracy & Speed)" },
    { value: "deepgram-nova-2", label: "Deepgram Nova-2 (Conversational English & Hindi)" },
    { value: "whisper-1", label: "OpenAI Whisper-1 (Accurate Multilingual)" },
    { value: "saaras:v2", label: "Sarvam Saaras v2 (High-accuracy Indic Speech)" },
    { value: "azure-stt", label: "Microsoft Azure Speech" },
];

export const LOCAL_STT_MODELS = [
    { value: "Systran/faster-whisper-base", label: "Faster-Whisper Base (Recommended CPU - English & Hindi)" },
    { value: "Systran/faster-whisper-small", label: "Faster-Whisper Small (High Accuracy CPU - English & Hindi)" },
    { value: "Systran/faster-whisper-tiny.en", label: "Faster-Whisper Tiny English (Fastest CPU)" },
];

export const CLOUD_TTS_MODELS = [
    { value: "auto", label: "Auto (Recommended - Best matched for voice)" },
    { value: "gemini-2.5-flash-preview-tts", label: "Google Gemini 2.5 Voice Studio (High Fidelity)" },
    { value: "sonic-3.5", label: "Cartesia Sonic 3.5 (Ultra-low latency, 90ms)" },
    { value: "sonic-multilingual", label: "Cartesia Sonic Multilingual" },
    { value: "eleven_flash_v2_5", label: "ElevenLabs Flash v2.5 (High Speed & Expressive)" },
    { value: "eleven_multilingual_v2", label: "ElevenLabs Multilingual v2 (Rich Neural)" },
    { value: "tts-1", label: "OpenAI TTS-1 (Standard Natural Speech)" },
    { value: "tts-1-hd", label: "OpenAI TTS-1 HD (High Definition Studio)" },
    { value: "bulbul:v1", label: "Sarvam Bulbul v1 (Native Indian Languages)" },
    { value: "deepgram-aura", label: "Deepgram Aura (Sub-150ms Conversational)" },
    { value: "azure-tts", label: "Microsoft Azure Neural Voice" },
];

export const LOCAL_TTS_MODELS = [
    { value: "piper", label: "Piper TTS (Native Hindi & Indic ONNX, ~40ms Ultra-Fast)" },
];

interface AIModelConfigurationV2EditorProps {
    defaults: ModelConfigurationDefaultsV2;
    configuration?: OrganizationAiModelConfigurationV2 | Record<string, unknown> | null;
    effectiveConfiguration?: Record<string, unknown> | null;
    pricing?: ModelConfigurationPricingResponse | null;
    onSave: (configuration: OrganizationAiModelConfigurationV2) => Promise<void>;
    submitLabel?: string;
}

function firstApiKey(value: unknown): string {
    if (Array.isArray(value)) return String(value[0] || "");
    return typeof value === "string" ? value : "";
}

function numberOrDefault(value: unknown, fallback: number): number {
    const parsed = typeof value === "number" ? value : Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function asRecord(value: unknown): Record<string, unknown> | null {
    return value && typeof value === "object" && !Array.isArray(value)
        ? value as Record<string, unknown>
        : null;
}

function isKodewavesEffectiveConfig(config: Record<string, unknown> | null | undefined): boolean {
    if (!config || config.is_realtime) return false;
    const llm = asRecord(config.llm);
    const tts = asRecord(config.tts);
    const stt = asRecord(config.stt);
    return (llm?.provider === "kodewaves" || llm?.provider === "dograh" || llm?.provider === "speaches") &&
           (tts?.provider === "kodewaves" || tts?.provider === "dograh" || tts?.provider === "speaches") &&
           (stt?.provider === "kodewaves" || stt?.provider === "dograh" || stt?.provider === "speaches");
}
const isDograhEffectiveConfig = isKodewavesEffectiveConfig;

function byokDefaults(defaults: ModelConfigurationDefaultsV2): ServiceConfigurationDefaults {
    return {
        llm: defaults.byok.pipeline.llm,
        tts: defaults.byok.pipeline.tts,
        stt: defaults.byok.pipeline.stt,
        embeddings: defaults.byok.pipeline.embeddings,
        realtime: defaults.byok.realtime.realtime,
        default_providers: defaults.byok.pipeline.default_providers,
    };
}

function byokConfigToLegacyShape(config: Record<string, unknown> | null): Record<string, unknown> | null {
    if (!config || config.mode !== "byok") return null;
    const byok = asRecord(config.byok);
    if (!byok) return null;

    if (byok.mode === "realtime") {
        const realtime = asRecord(byok.realtime);
        return {
            is_realtime: true,
            realtime: realtime?.realtime,
            llm: realtime?.llm,
            embeddings: realtime?.embeddings,
        };
    }

    const pipeline = asRecord(byok.pipeline);
    return {
        is_realtime: false,
        llm: pipeline?.llm,
        tts: pipeline?.tts,
        stt: pipeline?.stt,
        embeddings: pipeline?.embeddings,
    };
}

function effectiveConfigToLegacyShape(config: Record<string, unknown> | null): Record<string, unknown> | null {
    if (!config) return null;
    return {
        is_realtime: Boolean(config.is_realtime),
        llm: config.llm,
        tts: config.tts,
        stt: config.stt,
        realtime: config.realtime,
        embeddings: config.embeddings,
    };
}

function emptyByokInitialConfig(isRealtime: boolean): Record<string, unknown> {
    return {
        is_realtime: isRealtime,
    };
}

// The v2 editor surfaces realtime ("Speech to Speech") and pipeline (BYOK) as
// separate tabs, so each tab gets its own initial config. A tab is pre-filled
// only when the saved (or effective) configuration matches that tab's mode;
// otherwise it starts empty so the other tab's data does not leak across.
function getByokInitialConfig(
    configuration: Record<string, unknown> | null,
    effectiveConfiguration: Record<string, unknown> | null,
    wantRealtime: boolean,
): Record<string, unknown> {
    const matchesTab = (config: Record<string, unknown> | null) =>
        config ? Boolean(config.is_realtime) === wantRealtime : false;

    const byokConfiguration = byokConfigToLegacyShape(configuration);
    if (byokConfiguration) {
        return matchesTab(byokConfiguration) ? byokConfiguration : emptyByokInitialConfig(wantRealtime);
    }

    if (
        configuration?.mode === "kodewaves" ||
        configuration?.mode === "dograh" ||
        isKodewavesEffectiveConfig(effectiveConfiguration)
    ) {
        return emptyByokInitialConfig(wantRealtime);
    }

    const effective = effectiveConfigToLegacyShape(effectiveConfiguration);
    return matchesTab(effective) ? (effective as Record<string, unknown>) : emptyByokInitialConfig(wantRealtime);
}

function buildKodewavesState(
    defaults: ModelConfigurationDefaultsV2,
    configuration: Record<string, unknown> | null,
    effectiveConfiguration: Record<string, unknown> | null,
): KodewavesFormState {
    const fallback = (defaults.kodewaves || defaults.dograh).defaults;
    const configuredKodewaves =
        configuration?.mode === "kodewaves"
            ? asRecord(configuration.kodewaves || configuration.dograh)
            : configuration?.mode === "dograh"
            ? asRecord(configuration.dograh)
            : null;
    const cleanVoice = (v: unknown, lang?: string) => {
        const s = String(v || "");
        if (!s || s === "default" || s === "alloy" || s.startsWith("kw_") || s.startsWith("dg_") || s.startsWith("af_") || s.startsWith("am_") || s === "kokoro") {
            return "hi_IN-priya-medium";
        }
        if (s === "if_sara" || s === "im_nicola") {
            return "hi_IN-priya-medium";
        }
        return s;
    };

    if (configuredKodewaves) {
        const apiKey = String(configuredKodewaves.api_key || "");
        const isLocalCpu = apiKey === "sovereign-local-cpu" || apiKey.includes("local-cpu") || apiKey.endsWith("-cpu");
        const lang = String(configuredKodewaves.language || fallback.language);
        const llmModel = configuredKodewaves.llm_model ? String(configuredKodewaves.llm_model) : undefined;
        const sttModel = configuredKodewaves.stt_model ? String(configuredKodewaves.stt_model) : undefined;
        const ttsModel = configuredKodewaves.tts_model ? String(configuredKodewaves.tts_model) : undefined;
        const chosenVoice = cleanVoice(configuredKodewaves.voice || fallback.voice, lang);

        const llmEngineType = (configuredKodewaves.llm_engine_type as "cloud" | "local_cpu") ||
            (llmModel && (llmModel.startsWith("qwen") || llmModel.startsWith("llama3.2") || llmModel.startsWith("phi")) ? "local_cpu" : (isLocalCpu ? "local_cpu" : "cloud"));
        const sttEngineType = (configuredKodewaves.stt_engine_type as "cloud" | "local_cpu") ||
            (sttModel && sttModel.startsWith("Systran/") ? "local_cpu" : (isLocalCpu ? "local_cpu" : "cloud"));
        const ttsEngineType = (configuredKodewaves.tts_engine_type as "cloud" | "local_cpu") ||
            (ttsModel === "piper" || chosenVoice.startsWith("hi_IN-") || chosenVoice.startsWith("en_IN-") ? (isLocalCpu ? "local_cpu" : "cloud") : (isLocalCpu ? "local_cpu" : "cloud"));

        return {
            api_key: apiKey,
            voice: chosenVoice,
            speed: numberOrDefault(configuredKodewaves.speed, fallback.speed),
            language: lang,
            engine_type: isLocalCpu ? "local_cpu" : "cloud",
            llm_engine_type: llmEngineType,
            stt_engine_type: sttEngineType,
            tts_engine_type: ttsEngineType,
            llm_model: llmModel,
            stt_model: sttModel,
            tts_model: ttsModel,
        };
    }

    if (isKodewavesEffectiveConfig(effectiveConfiguration)) {
        const llm = asRecord(effectiveConfiguration?.llm);
        const tts = asRecord(effectiveConfiguration?.tts);
        const stt = asRecord(effectiveConfiguration?.stt);
        const apiKey = firstApiKey(llm?.api_key || tts?.api_key || stt?.api_key);
        const isLocalCpu = apiKey === "sovereign-local-cpu" || apiKey.includes("local-cpu") || apiKey.endsWith("-cpu") || llm?.provider === "speaches";
        const lang = String(stt?.language || fallback.language);
        const llmModel = llm?.model ? String(llm.model) : undefined;
        const sttModel = stt?.model ? String(stt.model) : undefined;
        const ttsModel = tts?.model ? String(tts.model) : undefined;
        const chosenVoice = cleanVoice(tts?.voice || fallback.voice, lang);

        const llmEngineType = (llm?.provider === "speaches" || (llmModel && llmModel.startsWith("qwen"))) ? "local_cpu" : "cloud";
        const sttEngineType = (stt?.provider === "speaches" || (sttModel && sttModel.startsWith("Systran/"))) ? "local_cpu" : "cloud";
        const ttsEngineType = (tts?.provider === "speaches" || tts?.provider === "piper" || ttsModel === "piper" || chosenVoice.startsWith("hi_IN-") || chosenVoice.startsWith("en_IN-")) ? "local_cpu" : "cloud";

        return {
            api_key: apiKey,
            voice: chosenVoice,
            speed: numberOrDefault(tts?.speed, fallback.speed),
            language: lang,
            engine_type: isLocalCpu ? "local_cpu" : "cloud",
            llm_engine_type: llmEngineType,
            stt_engine_type: sttEngineType,
            tts_engine_type: ttsEngineType,
            llm_model: llmModel,
            stt_model: sttModel,
            tts_model: ttsModel,
        };
    }

    return {
        api_key: "",
        voice: cleanVoice(fallback.voice, fallback.language),
        speed: fallback.speed,
        language: fallback.language,
        engine_type: "cloud",
        llm_engine_type: "cloud",
        stt_engine_type: "cloud",
        tts_engine_type: "cloud",
        llm_model: undefined,
        stt_model: undefined,
        tts_model: undefined,
    };
}
const buildDograhState = buildKodewavesState;

function preferredMode(
    configuration: Record<string, unknown> | null,
    effectiveConfiguration: Record<string, unknown> | null,
): ModelMode {
    if (configuration?.mode === "kodewaves" || configuration?.mode === "dograh") return "kodewaves";
    if (configuration?.mode === "byok") {
        return asRecord(configuration.byok)?.mode === "realtime" ? "realtime" : "byok";
    }
    if (isKodewavesEffectiveConfig(effectiveConfiguration)) return "kodewaves";
    return Boolean(effectiveConfiguration?.is_realtime) ? "realtime" : "byok";
}

function hasRequiredApiKey(
    service: ServiceSegment,
    serviceConfiguration: Record<string, unknown>,
    defaults: ServiceConfigurationDefaults,
): boolean {
    const provider = serviceConfiguration.provider as string | undefined;
    if (!provider) return false;
    const providerSchema = service === "realtime"
        ? defaults.realtime?.[provider]
        : defaults[service as "llm" | "tts" | "stt" | "embeddings"]?.[provider];
    const requiresApiKey = providerSchema?.required?.includes("api_key") ?? false;
    if (!requiresApiKey) return true;

    const apiKey = serviceConfiguration.api_key;
    if (Array.isArray(apiKey)) {
        return apiKey.some((key) => typeof key === "string" && key.trim().length > 0);
    }
    return typeof apiKey === "string" && apiKey.trim().length > 0;
}

function requireByokService(
    config: Record<string, unknown>,
    service: ServiceSegment,
    defaults: ServiceConfigurationDefaults,
): Record<string, unknown> {
    const serviceConfiguration = asRecord(config[service]);
    if (
        !serviceConfiguration
        || !serviceConfiguration.provider
        || serviceConfiguration.provider === "kodewaves"
        || serviceConfiguration.provider === "dograh"
        || !hasRequiredApiKey(service, serviceConfiguration, defaults)
    ) {
        throw new Error(`${service} configuration is required`);
    }
    return serviceConfiguration;
}

function optionalByokService(config: Record<string, unknown>, service: ServiceSegment): Record<string, unknown> | undefined {
    const serviceConfiguration = asRecord(config[service]);
    if (!serviceConfiguration?.provider || serviceConfiguration.provider === "kodewaves" || serviceConfiguration.provider === "dograh") return undefined;
    return serviceConfiguration;
}

function ThirdPartyProviderNotice() {
    return (
        <div className="mt-4 flex gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-900 dark:text-amber-200">
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
                <p className="font-medium">Third-party provider data notice</p>
                <p className="mt-1 leading-6">
                    Kodewaves sends data required by the selected model service. This may include prompts,
                    transcripts, audio, generated text, tool data, and request metadata depending on the
                    provider and service type. Review the provider&apos;s data and retention policies before
                    using sensitive data.
                </p>
            </div>
        </div>
    );
}

function formatPricePerMinute(price: ModelConfigurationMetricPrice): string {
    return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: price.currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 4,
    }).format(price.price_per_minute);
}

function MetricPrice({
    label,
    price,
}: {
    label: string;
    price: ModelConfigurationMetricPrice;
}) {
    return (
        <div className="space-y-0.5">
            <p className="text-muted-foreground">
                {label}: <span className="font-medium text-foreground">{formatPricePerMinute(price)}/{price.unit}</span>
            </p>
            <p className="text-xs text-muted-foreground">
                {formatRoundingPolicy(price.rounding_policy)}
            </p>
        </div>
    );
}

function PricingSummary({
    pricing,
    includeManagedModel,
    includeDograhModel,
    thirdPartyModels,
}: {
    pricing?: ModelConfigurationPricingResponse | null;
    includeManagedModel?: boolean;
    includeDograhModel?: boolean;
    thirdPartyModels?: boolean;
}) {
    const platformPrice = pricing?.platform_usage;
    const shouldInclude = includeManagedModel ?? includeDograhModel ?? false;
    const managedModelPrice = shouldInclude ? ((pricing as any)?.kodewaves_model || pricing?.dograh_model) : null;
    if (!platformPrice && !managedModelPrice) return null;

    return (
        <Card className="mb-4 border-primary/20 bg-primary/[0.03]">
            <CardContent className="space-y-2 pt-5 text-sm">
                <p className="font-medium">Usage pricing</p>
                {platformPrice && (
                    <MetricPrice label="Platform usage" price={platformPrice} />
                )}
                {managedModelPrice && (
                    <MetricPrice label="Managed model usage" price={managedModelPrice} />
                )}
                {thirdPartyModels && (
                    <p className="text-muted-foreground">
                        Your selected model provider may charge separately for its usage.
                    </p>
                )}
            </CardContent>
        </Card>
    );
}

export function AIModelConfigurationV2Editor({
    defaults,
    configuration,
    effectiveConfiguration,
    pricing,
    onSave,
    submitLabel = "Save Configuration",
}: AIModelConfigurationV2EditorProps) {
    const defaultsForByok = useMemo(() => byokDefaults(defaults), [defaults]);
    const [mode, setMode] = useState<ModelMode>("kodewaves");
    const kodewavesDefaults = defaults.kodewaves || defaults.dograh;
    const [kodewaves, setKodewaves] = useState<KodewavesFormState>(() => ({
        api_key: "",
        voice: kodewavesDefaults.defaults.voice,
        speed: kodewavesDefaults.defaults.speed,
        language: kodewavesDefaults.defaults.language,
    }));
    const [realtimeInitialConfig, setRealtimeInitialConfig] = useState<Record<string, unknown> | null>(null);
    const [pipelineInitialConfig, setPipelineInitialConfig] = useState<Record<string, unknown> | null>(null);
    const [isSavingKodewaves, setIsSavingKodewaves] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const allowCustomVoice = kodewavesDefaults.allow_custom_input ?? false;
    const kodewavesSpeedRange = kodewavesDefaults.speed_range ?? { min: 0.5, max: 2.0, step: 0.1 };
    const multilingualLanguageNames = useMemo(() => {
        const codes = kodewavesDefaults.multilingual_languages ?? [];
        if (codes.length === 0) return null;
        return codes.map((code) => LANGUAGE_DISPLAY_NAMES[code] || code).join(", ");
    }, [kodewavesDefaults.multilingual_languages]);

    const [catalogManifest, setCatalogManifest] = useState<AvailableCatalogResponse | null>(null);

    useEffect(() => {
        catalogApi.getAvailableCatalog()
            .then((data) => setCatalogManifest(data))
            .catch((err) => console.warn("[AIModelConfigurationV2Editor] Failed to fetch dynamic catalog:", err));
    }, []);

    const effectiveLlmModels = useMemo(() => {
        const isLocal = kodewaves.llm_engine_type === "local_cpu";
        if (isLocal) {
            if (catalogManifest?.local_llm_models && catalogManifest.local_llm_models.length > 0) {
                return catalogManifest.local_llm_models;
            }
            return [
                { value: "qwen2.5:1.5b", label: "Qwen 2.5 1.5B (Installed CPU, ~980MB RAM)" },
                { value: "qwen2.5:0.5b", label: "Qwen 2.5 0.5B (Installed CPU, ~350MB RAM)" },
            ];
        }
        if (catalogManifest?.cloud_llm_models && catalogManifest.cloud_llm_models.length > 0) {
            return catalogManifest.cloud_llm_models;
        }
        return CLOUD_LLM_MODELS;
    }, [kodewaves.llm_engine_type, catalogManifest]);

    const effectiveSttModels = useMemo(() => {
        const isLocal = kodewaves.stt_engine_type === "local_cpu";
        if (isLocal) {
            if (catalogManifest?.local_stt_models && catalogManifest.local_stt_models.length > 0) {
                return catalogManifest.local_stt_models;
            }
            return LOCAL_STT_MODELS;
        }
        if (catalogManifest?.cloud_stt_models && catalogManifest.cloud_stt_models.length > 0) {
            return catalogManifest.cloud_stt_models;
        }
        return CLOUD_STT_MODELS;
    }, [kodewaves.stt_engine_type, catalogManifest]);

    const effectiveTtsModels = useMemo(() => {
        const isLocal = kodewaves.tts_engine_type === "local_cpu";
        if (isLocal) {
            if (catalogManifest?.local_tts_models && catalogManifest.local_tts_models.length > 0) {
                return catalogManifest.local_tts_models;
            }
            return LOCAL_TTS_MODELS;
        }
        if (catalogManifest?.cloud_tts_models && catalogManifest.cloud_tts_models.length > 0) {
            return catalogManifest.cloud_tts_models;
        }
        return CLOUD_TTS_MODELS;
    }, [kodewaves.tts_engine_type, catalogManifest]);

    useEffect(() => {
        const rawConfiguration = asRecord(configuration);
        const rawEffectiveConfiguration = asRecord(effectiveConfiguration);
        setMode(preferredMode(rawConfiguration, rawEffectiveConfiguration));
        const nextKodewaves = buildKodewavesState(defaults, rawConfiguration, rawEffectiveConfiguration);
        setKodewaves(nextKodewaves);
        setRealtimeInitialConfig(getByokInitialConfig(rawConfiguration, rawEffectiveConfiguration, true));
        setPipelineInitialConfig(getByokInitialConfig(rawConfiguration, rawEffectiveConfiguration, false));
    }, [configuration, defaults, effectiveConfiguration, allowCustomVoice]);

    const saveKodewavesConfiguration = async () => {
        setIsSavingKodewaves(true);
        setError(null);
        try {
            if (
                !Number.isFinite(kodewaves.speed)
                || kodewaves.speed < kodewavesSpeedRange.min
                || kodewaves.speed > kodewavesSpeedRange.max
            ) {
                throw new Error(
                    `Voice speed must be between ${kodewavesSpeedRange.min} and ${kodewavesSpeedRange.max}.`,
                );
            }
            const isAllLocal = kodewaves.llm_engine_type === "local_cpu" && kodewaves.stt_engine_type === "local_cpu" && kodewaves.tts_engine_type === "local_cpu";
            const apiKey = isAllLocal ? "sovereign-local-cpu" : "sovereign-managed";
            await onSave({
                version: 2,
                mode: "kodewaves",
                kodewaves: {
                    api_key: apiKey,
                    voice: kodewaves.voice,
                    speed: kodewaves.speed,
                    language: kodewaves.language,
                    llm_engine_type: kodewaves.llm_engine_type,
                    stt_engine_type: kodewaves.stt_engine_type,
                    tts_engine_type: kodewaves.tts_engine_type,
                    llm_model: kodewaves.llm_model || undefined,
                    stt_model: kodewaves.stt_model || undefined,
                    tts_model: kodewaves.tts_model || undefined,
                },
                dograh: {
                    api_key: apiKey,
                    voice: kodewaves.voice,
                    speed: kodewaves.speed,
                    language: kodewaves.language,
                    llm_engine_type: kodewaves.llm_engine_type,
                    stt_engine_type: kodewaves.stt_engine_type,
                    tts_engine_type: kodewaves.tts_engine_type,
                    llm_model: kodewaves.llm_model || undefined,
                    stt_model: kodewaves.stt_model || undefined,
                    tts_model: kodewaves.tts_model || undefined,
                },
            });
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to save configuration");
        } finally {
            setIsSavingKodewaves(false);
        }
    };
    const saveDograhConfiguration = saveKodewavesConfiguration;

    const saveByokConfiguration = async (config: Record<string, unknown>) => {
        setError(null);
        const isRealtime = Boolean(config.is_realtime);
        const llm = requireByokService(config, "llm", defaultsForByok);
        const embeddings = optionalByokService(config, "embeddings");
        const body: OrganizationAiModelConfigurationV2 = {
            version: 2,
            mode: "byok",
            byok: isRealtime
                ? {
                    mode: "realtime",
                    realtime: {
                        realtime: requireByokService(config, "realtime", defaultsForByok) as never,
                        llm: llm as never,
                        ...(embeddings ? { embeddings: embeddings as never } : {}),
                    },
                }
                : {
                    mode: "pipeline",
                    pipeline: {
                        llm: llm as never,
                        tts: requireByokService(config, "tts", defaultsForByok) as never,
                        stt: requireByokService(config, "stt", defaultsForByok) as never,
                        ...(embeddings ? { embeddings: embeddings as never } : {}),
                    },
                },
        };

        await onSave(body);
    };

    const activeTab = mode === "dograh" ? "kodewaves" : mode;

    return (
        <div className="space-y-6">
            {error && (
                <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                    {error}
                </div>
            )}

            <Tabs value={activeTab} onValueChange={(value) => setMode(value as ModelMode)} className="space-y-6">
                <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="realtime">Speech to Speech</TabsTrigger>
                    <TabsTrigger value="kodewaves">Managed Voice</TabsTrigger>
                    <TabsTrigger value="byok">BYOK</TabsTrigger>
                </TabsList>

                <TabsContent value="realtime" className="mt-0">
                    <p className="mb-4 text-sm text-muted-foreground">
                        A single speech-to-speech model handles the conversation in realtime (no separate transcriber or voice). An LLM is still required for variable extraction and QA.
                    </p>
                    <PricingSummary pricing={pricing} includeManagedModel={false} thirdPartyModels />
                    <ServiceConfigurationForm
                        key={`realtime-${JSON.stringify(realtimeInitialConfig)}`}
                        mode="global"
                        forceRealtime
                        configurationDefaults={defaultsForByok}
                        initialConfig={realtimeInitialConfig}
                        submitLabel={submitLabel}
                        onSave={saveByokConfiguration}
                    />
                    <ThirdPartyProviderNotice />
                </TabsContent>

                <TabsContent value="kodewaves" className="mt-0">
                    <p className="mb-4 text-sm text-muted-foreground">
                        Sovereign managed transcriber, LLM, and voice pipeline. Select a voice and language while Kodewaves manages the underlying model orchestration.
                    </p>
                    <PricingSummary pricing={pricing} includeManagedModel />
                    <Card>
                        <CardContent className="pt-6">
                            <div className="grid gap-4 sm:grid-cols-2">
                                {/* Pipeline Overview Banner */}
                                <div className="rounded-xl border border-primary/20 bg-primary/5 p-3.5 sm:col-span-2">
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                        <div className="flex items-center gap-2">
                                            <Cpu className="h-4 w-4 text-primary" />
                                            <span className="text-xs font-semibold text-foreground">Independent Layer Configuration</span>
                                        </div>
                                        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                                            <span className="rounded-md border bg-background px-2 py-0.5 font-medium text-muted-foreground">
                                                LLM: <strong className="text-foreground">{kodewaves.llm_engine_type === "local_cpu" ? "🖥️ Local" : "☁️ Cloud"}</strong>
                                            </span>
                                            <span className="rounded-md border bg-background px-2 py-0.5 font-medium text-muted-foreground">
                                                STT: <strong className="text-foreground">{kodewaves.stt_engine_type === "local_cpu" ? "🖥️ Local" : "☁️ Cloud"}</strong>
                                            </span>
                                            <span className="rounded-md border bg-background px-2 py-0.5 font-medium text-muted-foreground">
                                                TTS: <strong className="text-foreground">{kodewaves.tts_engine_type === "local_cpu" ? "🖥️ Local" : "☁️ Cloud"}</strong>
                                            </span>
                                        </div>
                                    </div>
                                    <p className="mt-1 text-[11px] text-muted-foreground">
                                        Mix and match cloud master keys and local CPU engines independently for each layer based on your latency and cost preferences.
                                    </p>
                                </div>

                                {/* LLM Model Selector */}
                                <div className="space-y-2 sm:col-span-2">
                                    <div className="flex items-center justify-between">
                                        <Label className="flex items-center gap-1.5 font-semibold text-xs text-foreground">
                                            <Bot className="h-4 w-4 text-primary" />
                                            LLM Model (Intelligence Engine)
                                        </Label>
                                        <div className="flex items-center gap-1 rounded-lg border bg-muted/30 p-0.5 text-[11px]">
                                            <button
                                                type="button"
                                                onClick={() => setKodewaves({ ...kodewaves, llm_engine_type: "cloud" })}
                                                className={`flex items-center gap-1 rounded-md px-2 py-0.5 font-medium transition-all ${
                                                    kodewaves.llm_engine_type !== "local_cpu"
                                                        ? "bg-primary text-primary-foreground shadow-xs"
                                                        : "text-muted-foreground hover:text-foreground"
                                                }`}
                                            >
                                                <Cloud className="h-3 w-3" /> Cloud
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    if (catalogManifest && catalogManifest.has_local_ai_access === false) return;
                                                    setKodewaves({ ...kodewaves, llm_engine_type: "local_cpu" });
                                                }}
                                                className={`flex items-center gap-1 rounded-md px-2 py-0.5 font-medium transition-all ${
                                                    kodewaves.llm_engine_type === "local_cpu"
                                                        ? "bg-amber-500 text-white shadow-xs"
                                                        : "text-muted-foreground hover:text-foreground"
                                                }`}
                                            >
                                                <Cpu className="h-3 w-3" /> Local CPU
                                            </button>
                                        </div>
                                    </div>
                                    <Select
                                        disabled={effectiveLlmModels.length === 0}
                                        value={
                                            effectiveLlmModels.length === 0
                                                ? "none"
                                                : (kodewaves.llm_model && effectiveLlmModels.some((m) => m.value === kodewaves.llm_model)
                                                    ? kodewaves.llm_model
                                                    : (effectiveLlmModels[0]?.value || "auto"))
                                        }
                                        onValueChange={(llm_model) => setKodewaves({ ...kodewaves, llm_model: llm_model === "auto" || llm_model === "none" ? undefined : llm_model })}
                                    >
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder={effectiveLlmModels.length === 0 ? "No active models available" : "Select LLM model"} />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {effectiveLlmModels.length === 0 ? (
                                                <SelectItem key="none" value="none" disabled>
                                                    {kodewaves.llm_engine_type === "local_cpu"
                                                        ? "No local Ollama models installed (Download in Admin > Settings)"
                                                        : "No active cloud master keys (Add keys in Admin > Models)"}
                                                </SelectItem>
                                            ) : (
                                                effectiveLlmModels.map((m) => (
                                                    <SelectItem key={m.value} value={m.value}>
                                                        {m.label}
                                                    </SelectItem>
                                                ))
                                            )}
                                        </SelectContent>
                                    </Select>
                                </div>

                                {/* STT Model Selector */}
                                <div className="space-y-2 sm:col-span-2">
                                    <div className="flex items-center justify-between">
                                        <Label className="flex items-center gap-1.5 font-semibold text-xs text-foreground">
                                            <Mic className="h-4 w-4 text-primary" />
                                            Transcriber (STT) Model
                                        </Label>
                                        <div className="flex items-center gap-1 rounded-lg border bg-muted/30 p-0.5 text-[11px]">
                                            <button
                                                type="button"
                                                onClick={() => setKodewaves({ ...kodewaves, stt_engine_type: "cloud" })}
                                                className={`flex items-center gap-1 rounded-md px-2 py-0.5 font-medium transition-all ${
                                                    kodewaves.stt_engine_type !== "local_cpu"
                                                        ? "bg-primary text-primary-foreground shadow-xs"
                                                        : "text-muted-foreground hover:text-foreground"
                                                }`}
                                            >
                                                <Cloud className="h-3 w-3" /> Cloud
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    if (catalogManifest && catalogManifest.has_local_ai_access === false) return;
                                                    setKodewaves({ ...kodewaves, stt_engine_type: "local_cpu" });
                                                }}
                                                className={`flex items-center gap-1 rounded-md px-2 py-0.5 font-medium transition-all ${
                                                    kodewaves.stt_engine_type === "local_cpu"
                                                        ? "bg-amber-500 text-white shadow-xs"
                                                        : "text-muted-foreground hover:text-foreground"
                                                }`}
                                            >
                                                <Cpu className="h-3 w-3" /> Local CPU
                                            </button>
                                        </div>
                                    </div>
                                    <Select
                                        disabled={effectiveSttModels.length === 0}
                                        value={
                                            effectiveSttModels.length === 0
                                                ? "none"
                                                : (kodewaves.stt_model && effectiveSttModels.some((m) => m.value === kodewaves.stt_model)
                                                    ? kodewaves.stt_model
                                                    : (effectiveSttModels[0]?.value || "auto"))
                                        }
                                        onValueChange={(stt_model) => setKodewaves({ ...kodewaves, stt_model: stt_model === "auto" || stt_model === "none" ? undefined : stt_model })}
                                    >
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder={effectiveSttModels.length === 0 ? "No active transcribers available" : "Select STT model"} />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {effectiveSttModels.length === 0 ? (
                                                <SelectItem key="none" value="none" disabled>
                                                    {kodewaves.stt_engine_type === "local_cpu"
                                                        ? "Local Speaches Whisper STT unavailable"
                                                        : "No active transcriber keys (Add Deepgram / Sarvam in Admin > Models)"}
                                                </SelectItem>
                                            ) : (
                                                effectiveSttModels.map((m) => (
                                                    <SelectItem key={m.value} value={m.value}>
                                                        {m.label}
                                                    </SelectItem>
                                                ))
                                            )}
                                        </SelectContent>
                                    </Select>
                                </div>

                                {/* TTS Model Selector */}
                                <div className="space-y-2 sm:col-span-2">
                                    <div className="flex items-center justify-between">
                                        <Label className="flex items-center gap-1.5 font-semibold text-xs text-foreground">
                                            <Volume2 className="h-4 w-4 text-primary" />
                                            Synthesizer (TTS) Model
                                        </Label>
                                        <div className="flex items-center gap-1 rounded-lg border bg-muted/30 p-0.5 text-[11px]">
                                            <button
                                                type="button"
                                                onClick={() => setKodewaves({ ...kodewaves, tts_engine_type: "cloud" })}
                                                className={`flex items-center gap-1 rounded-md px-2 py-0.5 font-medium transition-all ${
                                                    kodewaves.tts_engine_type !== "local_cpu"
                                                        ? "bg-primary text-primary-foreground shadow-xs"
                                                        : "text-muted-foreground hover:text-foreground"
                                                }`}
                                            >
                                                <Cloud className="h-3 w-3" /> Cloud
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    if (catalogManifest && catalogManifest.has_local_ai_access === false) return;
                                                    setKodewaves({ ...kodewaves, tts_engine_type: "local_cpu" });
                                                }}
                                                className={`flex items-center gap-1 rounded-md px-2 py-0.5 font-medium transition-all ${
                                                    kodewaves.tts_engine_type === "local_cpu"
                                                        ? "bg-amber-500 text-white shadow-xs"
                                                        : "text-muted-foreground hover:text-foreground"
                                                }`}
                                            >
                                                <Cpu className="h-3 w-3" /> Local CPU
                                            </button>
                                        </div>
                                    </div>
                                    <Select
                                        disabled={effectiveTtsModels.length === 0}
                                        value={
                                            effectiveTtsModels.length === 0
                                                ? "none"
                                                : (kodewaves.tts_model && effectiveTtsModels.some((m) => m.value === kodewaves.tts_model)
                                                    ? kodewaves.tts_model
                                                    : (effectiveTtsModels[0]?.value || "auto"))
                                        }
                                        onValueChange={(tts_model) => setKodewaves({ ...kodewaves, tts_model: tts_model === "auto" || tts_model === "none" ? undefined : tts_model })}
                                    >
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder={effectiveTtsModels.length === 0 ? "No active synthesizers available" : "Select TTS model"} />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {effectiveTtsModels.length === 0 ? (
                                                <SelectItem key="none" value="none" disabled>
                                                    {kodewaves.tts_engine_type === "local_cpu"
                                                        ? "Local Piper ONNX TTS unavailable"
                                                        : "No active synthesizer keys (Add Cartesia / ElevenLabs in Admin > Models)"}
                                                </SelectItem>
                                            ) : (
                                                effectiveTtsModels.map((m) => (
                                                    <SelectItem key={m.value} value={m.value}>
                                                        {m.label}
                                                    </SelectItem>
                                                ))
                                            )}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-2 sm:col-span-2">
                                    <Label>Voice</Label>
                                    <VoiceSelectorModal
                                        provider={kodewaves.tts_engine_type === "local_cpu" ? "piper" : "kodewaves"}
                                        value={kodewaves.voice}
                                        onChange={(voice) => setKodewaves({ ...kodewaves, voice })}
                                        allowManualInput={allowCustomVoice}
                                    />
                                </div>

                                <div className="space-y-2 sm:col-span-2">
                                    <Label>Language</Label>
                                    <Select value={kodewaves.language} onValueChange={(language) => setKodewaves({ ...kodewaves, language })}>
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder="Select language" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {kodewavesDefaults.languages.map((language) => (
                                                <SelectItem key={language} value={language}>
                                                    {LANGUAGE_DISPLAY_NAMES[language] || language}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    {kodewaves.language === MULTILINGUAL_LANGUAGE_CODE && multilingualLanguageNames && (
                                        <p className="text-xs text-muted-foreground">
                                            Auto-detects {multilingualLanguageNames}.
                                        </p>
                                    )}
                                </div>

                                <div className="space-y-2 sm:col-span-2">
                                    <Label htmlFor="kodewaves-speed">Speed</Label>
                                    <Input
                                        id="kodewaves-speed"
                                        type="number"
                                        min={kodewavesSpeedRange.min}
                                        max={kodewavesSpeedRange.max}
                                        step={kodewavesSpeedRange.step ?? 0.1}
                                        value={kodewaves.speed}
                                        onChange={(event) => {
                                            const speed = event.currentTarget.valueAsNumber;
                                            setKodewaves({
                                                ...kodewaves,
                                                speed: Number.isFinite(speed) ? speed : kodewavesDefaults.defaults.speed,
                                            });
                                        }}
                                    />
                                </div>

                                {kodewaves.engine_type === "local_cpu" ? (
                                    <div className="sm:col-span-2 p-4 rounded-xl border border-amber-500/30 bg-amber-500/10 flex items-start gap-3">
                                        <Cpu className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
                                        <div className="space-y-1 text-xs">
                                            <div className="font-semibold text-foreground text-sm flex items-center gap-2">
                                                Local Sovereign CPU Engine Active
                                                <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-600 dark:text-amber-400 font-bold uppercase tracking-wider">
                                                    Zero Cloud Keys Required
                                                </span>
                                            </div>
                                            <p className="text-muted-foreground leading-relaxed">
                                                Voice pipeline calls run exclusively on your server CPU via Ollama (Qwen2.5) and Speaches (Faster-Whisper STT & Piper Native Indic ONNX TTS). Completely sovereign, reliable, and consumes zero wallet minutes.
                                            </p>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="sm:col-span-2 p-4 rounded-xl border border-primary/20 bg-primary/5 flex items-start gap-3">
                                        <ShieldCheck className="h-5 w-5 text-primary shrink-0 mt-0.5" />
                                        <div className="space-y-1 text-xs">
                                            <div className="font-semibold text-foreground text-sm">
                                                Sovereign Platform Managed (Admin Master Keys)
                                            </div>
                                            <p className="text-muted-foreground leading-relaxed">
                                                Voice pipelines run seamlessly using the master provider keys configured in your Admin Panel (Google Gemini, OpenAI, Deepgram, Sarvam, Cartesia, ElevenLabs). Voice usage is billed in minutes from your organization balance.
                                            </p>
                                        </div>
                                    </div>
                                )}
                            </div>

                            <Button type="button" className="mt-6 w-full" onClick={saveKodewavesConfiguration} disabled={isSavingKodewaves}>
                                <Save className="mr-2 h-4 w-4" />
                                {isSavingKodewaves ? "Saving..." : submitLabel}
                            </Button>
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="byok" className="mt-0">
                    <p className="mb-4 text-sm text-muted-foreground">
                        Configure separate transcriber, LLM, and voice providers using your own API keys. An embeddings model can also be configured for knowledge retrieval.
                    </p>
                    <PricingSummary pricing={pricing} includeManagedModel={false} thirdPartyModels />
                    <ServiceConfigurationForm
                        key={`byok-${JSON.stringify(pipelineInitialConfig)}`}
                        mode="global"
                        forceRealtime={false}
                        configurationDefaults={defaultsForByok}
                        initialConfig={pipelineInitialConfig}
                        submitLabel={submitLabel}
                        onSave={saveByokConfiguration}
                    />
                    <ThirdPartyProviderNotice />
                </TabsContent>
            </Tabs>
        </div>
    );
}
