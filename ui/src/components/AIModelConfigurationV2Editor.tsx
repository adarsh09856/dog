"use client";

import { AlertTriangle, Bot, CheckCircle2, Cloud, Cpu, Info, Key, Layers, Mic, Save, ShieldCheck, Sparkles, Volume2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getVoicesApiV1UserConfigurationsVoicesProviderGet } from "@/client/sdk.gen";
import { detailFromError } from "@/lib/apiError";

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
import { useAuth } from "@/lib/auth";

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
    is_realtime?: boolean;
    realtime_provider?: string;
    realtime_model?: string;
}
export type DograhFormState = KodewavesFormState;

export const GEMINI_LIVE_VOICES = [
    { value: "Puck", label: "Puck (Natural & Conversational)" },
    { value: "Charon", label: "Charon (Warm & Confident)" },
    { value: "Kore", label: "Kore (Bright & Engaging)" },
    { value: "Fenrir", label: "Fenrir (Authoritative & Deep)" },
    { value: "Aoede", label: "Aoede (Melodic & Expressive)" },
];

export const OPENAI_REALTIME_VOICES = [
    { value: "alloy", label: "Alloy (Neutral & Balanced)" },
    { value: "echo", label: "Echo (Smooth & Warm)" },
    { value: "shimmer", label: "Shimmer (Expressive & Clear)" },
    { value: "ash", label: "Ash (Casual & Friendly)" },
    { value: "ballad", label: "Ballad (Resonant & Melodic)" },
    { value: "coral", label: "Coral (Energetic & Friendly)" },
    { value: "sage", label: "Sage (Calm & Wise)" },
    { value: "verse", label: "Verse (Dynamic & Crisp)" },
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
        if (!s || s === "default" || s.startsWith("kw_") || s.startsWith("dg_") || s.startsWith("af_") || s.startsWith("am_")) {
            return "Puck";
        }
        if (s === "if_sara" || s === "im_nicola" || s === "hi_IN-priya-medium") {
            return "hi_IN-priyamvada-medium";
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
            (llmModel && (llmModel.startsWith("qwen") || llmModel.startsWith("llama3.2") || llmModel.startsWith("phi")) ? "local_cpu" : "cloud");
        const sttEngineType = (configuredKodewaves.stt_engine_type as "cloud" | "local_cpu") ||
            (sttModel && sttModel.startsWith("Systran/") ? "local_cpu" : "cloud");
        const ttsEngineType = (configuredKodewaves.tts_engine_type as "cloud" | "local_cpu") ||
            (ttsModel === "piper" || (chosenVoice.startsWith("hi_IN-") && !["Journey", "Puck", "Charon", "Aoede", "Fenrir", "Kore", "alloy"].includes(chosenVoice)) ? "local_cpu" : "cloud");

        const isRealtime = Boolean(configuredKodewaves.is_realtime);
        const realtimeProvider = configuredKodewaves.realtime_provider ? String(configuredKodewaves.realtime_provider) : "google";
        const realtimeModel = configuredKodewaves.realtime_model ? String(configuredKodewaves.realtime_model) : "";

        return {
            api_key: apiKey,
            voice: chosenVoice,
            speed: numberOrDefault(configuredKodewaves.speed, fallback.speed),
            language: lang,
            engine_type: (llmEngineType === "local_cpu" && sttEngineType === "local_cpu" && ttsEngineType === "local_cpu") ? "local_cpu" : "cloud",
            llm_engine_type: llmEngineType,
            stt_engine_type: sttEngineType,
            tts_engine_type: ttsEngineType,
            llm_model: llmModel,
            stt_model: sttModel,
            tts_model: ttsModel,
            is_realtime: isRealtime,
            realtime_provider: realtimeProvider,
            realtime_model: realtimeModel,
        };
    }

    if (isKodewavesEffectiveConfig(effectiveConfiguration)) {
        const llm = asRecord(effectiveConfiguration?.llm);
        const tts = asRecord(effectiveConfiguration?.tts);
        const stt = asRecord(effectiveConfiguration?.stt);
        const apiKey = firstApiKey(llm?.api_key || tts?.api_key || stt?.api_key);
        const lang = String(stt?.language || fallback.language);
        const llmModel = llm?.model ? String(llm.model) : undefined;
        const sttModel = stt?.model ? String(stt.model) : undefined;
        const ttsModel = tts?.model ? String(tts.model) : undefined;
        const chosenVoice = cleanVoice(tts?.voice || fallback.voice, lang);

        const llmEngineType = (llm?.provider === "speaches" || (llmModel && llmModel.startsWith("qwen"))) ? "local_cpu" : "cloud";
        const sttEngineType = (stt?.provider === "speaches" || (sttModel && sttModel.startsWith("Systran/"))) ? "local_cpu" : "cloud";
        const ttsEngineType = (tts?.provider === "speaches" || tts?.provider === "piper" || ttsModel === "piper") ? "local_cpu" : "cloud";

        return {
            api_key: apiKey,
            voice: chosenVoice,
            speed: numberOrDefault(tts?.speed, fallback.speed),
            language: lang,
            engine_type: (llmEngineType === "local_cpu" && sttEngineType === "local_cpu" && ttsEngineType === "local_cpu") ? "local_cpu" : "cloud",
            llm_engine_type: llmEngineType,
            stt_engine_type: sttEngineType,
            tts_engine_type: ttsEngineType,
            llm_model: llmModel,
            stt_model: sttModel,
            tts_model: ttsModel,
            is_realtime: false,
            realtime_provider: "google",
            realtime_model: "",
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
        is_realtime: false,
        realtime_provider: "google",
        realtime_model: "",
    };
}
const buildDograhState = buildKodewavesState;

function preferredMode(
    configuration: Record<string, unknown> | null,
    effectiveConfiguration: Record<string, unknown> | null,
): ModelMode {
    if (configuration?.mode === "kodewaves" || configuration?.mode === "dograh") {
        const kw = asRecord(configuration.kodewaves || configuration.dograh);
        if (kw?.is_realtime) return "realtime";
        return "kodewaves";
    }
    if (configuration?.mode === "byok") {
        return asRecord(configuration.byok)?.mode === "realtime" ? "realtime" : "byok";
    }
    if (isKodewavesEffectiveConfig(effectiveConfiguration)) return "kodewaves";
    return Boolean(effectiveConfiguration?.is_realtime) ? "realtime" : "kodewaves";
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
    const { user, loading: authLoading } = useAuth();
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
    const [catalogManifest, setCatalogManifest] = useState<AvailableCatalogResponse | null>(null);
    const [catalogError, setCatalogError] = useState<string | null>(null);

    useEffect(() => {
        if (authLoading || !user) return;
        let active = true;
        const refreshCatalog = () => {
            catalogApi.getAvailableCatalog()
                .then((data) => { if (active) { setCatalogManifest(data); setCatalogError(null); } })
                .catch(() => { if (active) setCatalogError("Could not refresh available models. Check the connection before saving."); });
        };
        refreshCatalog();
        window.addEventListener("focus", refreshCatalog);
        window.addEventListener("kodewaves-model-catalog-changed", refreshCatalog);
        const onStorage = (event: StorageEvent) => {
            if (event.key === "kodewaves-model-catalog-revision") refreshCatalog();
        };
        window.addEventListener("storage", onStorage);
        return () => {
            active = false;
            window.removeEventListener("focus", refreshCatalog);
            window.removeEventListener("kodewaves-model-catalog-changed", refreshCatalog);
            window.removeEventListener("storage", onStorage);
        };
    }, [authLoading, user]);

    const effectiveLlmModels = useMemo(() => {
        const isLocal = kodewaves.llm_engine_type === "local_cpu";
        if (isLocal) {
            return catalogManifest?.local_llm_models || [];
        }
        let list = catalogManifest?.cloud_llm_models || [];
        
        const activeProvs = catalogManifest?.active_providers;
        if (activeProvs && activeProvs.length > 0) {
            const allowed = new Set(activeProvs.map((p) => p.toLowerCase()));
            if (allowed.has("gemini")) allowed.add("google");
            if (allowed.has("google")) allowed.add("gemini");
            list = list.filter((m: any) => {
                const prov = (m.provider || "").toLowerCase();
                return prov === "auto" || allowed.has(prov) || m.has_master_key;
            });
        }
        return list;
    }, [kodewaves.llm_engine_type, catalogManifest]);

    const effectiveSttModels = useMemo(() => {
        const isLocal = kodewaves.stt_engine_type === "local_cpu";
        if (isLocal) {
            return catalogManifest?.local_stt_models || [];
        }
        let list = catalogManifest?.cloud_stt_models || [];
        
        const activeProvs = catalogManifest?.active_providers;
        if (activeProvs && activeProvs.length > 0) {
            const allowed = new Set(activeProvs.map((p) => p.toLowerCase()));
            if (allowed.has("gemini")) allowed.add("google");
            if (allowed.has("google")) allowed.add("gemini");
            list = list.filter((m: any) => {
                const prov = (m.provider || "").toLowerCase();
                return prov === "auto" || allowed.has(prov) || m.has_master_key;
            });
        }
        return list;
    }, [kodewaves.stt_engine_type, catalogManifest]);

    const setRecognitionLanguage = (language: string) => {
        if (language === MULTILINGUAL_LANGUAGE_CODE
            && kodewaves.stt_engine_type === "local_cpu"
            && kodewaves.stt_model === "indicconformer-ctc-int8") {
            setError("Self-hosted STT needs one selected installed language. Choose a language, or switch STT to cloud for automatic detection.");
            return;
        }
        setKodewaves({ ...kodewaves, language });
        setError(null);
    };

    const effectiveTtsModels = useMemo(() => {
        const isLocal = kodewaves.tts_engine_type === "local_cpu";
        if (isLocal) {
            return catalogManifest?.local_tts_models || [];
        }
        let list = catalogManifest?.cloud_tts_models || [];
        
        const activeProvs = catalogManifest?.active_providers;
        if (activeProvs && activeProvs.length > 0) {
            const allowed = new Set(activeProvs.map((p) => p.toLowerCase()));
            if (allowed.has("gemini")) allowed.add("google");
            if (allowed.has("google")) allowed.add("gemini");
            list = list.filter((m: any) => {
                const prov = (m.provider || "").toLowerCase();
                return prov === "auto" || allowed.has(prov) || m.has_master_key;
            });
        }
        return list;
    }, [kodewaves.tts_engine_type, catalogManifest]);

    const effectiveTtsProvider = useMemo(() => {
        if (kodewaves.tts_engine_type === "local_cpu") {
            return effectiveTtsModels.find(model => model.value === kodewaves.tts_model)?.provider || "all";
        }
        const selectedProvider = effectiveTtsModels.find(model => model.value === kodewaves.tts_model)?.provider;
        return selectedProvider && selectedProvider !== "auto" ? selectedProvider : "all";
    }, [kodewaves.tts_engine_type, kodewaves.tts_model, effectiveTtsModels]);

    const effectiveS2sModels = useMemo(() => {
        let list = catalogManifest?.cloud_s2s_models || [];
        const activeProvs = catalogManifest?.active_providers;
        if (activeProvs && activeProvs.length > 0) {
            const allowed = new Set(activeProvs.map((p) => p.toLowerCase()));
            if (allowed.has("gemini")) allowed.add("google");
            if (allowed.has("google")) allowed.add("gemini");
            list = list.filter((m: any) => {
                const prov = (m.provider || "").toLowerCase();
                return allowed.has(prov) || m.has_master_key;
            });
        }
        return list;
    }, [catalogManifest]);

    const effectiveS2sVoices = useMemo(() => {
        const prov = (kodewaves.realtime_provider || "google").toLowerCase();
        if (prov === "openai") return OPENAI_REALTIME_VOICES;
        return GEMINI_LIVE_VOICES;
    }, [kodewaves.realtime_provider]);

    const [showRealtimeByok, setShowRealtimeByok] = useState(false);

    useEffect(() => {
        const rawConfiguration = asRecord(configuration);
        const rawEffectiveConfiguration = asRecord(effectiveConfiguration);
        setMode(preferredMode(rawConfiguration, rawEffectiveConfiguration));
        const nextKodewaves = buildKodewavesState(defaults, rawConfiguration, rawEffectiveConfiguration);
        setKodewaves(nextKodewaves);
        setRealtimeInitialConfig(getByokInitialConfig(rawConfiguration, rawEffectiveConfiguration, true));
        setPipelineInitialConfig(getByokInitialConfig(rawConfiguration, rawEffectiveConfiguration, false));
    }, [configuration, defaults, effectiveConfiguration, allowCustomVoice]);

    const saveKodewavesConfiguration = async (overrideRealtime?: boolean) => {
        setIsSavingKodewaves(true);
        setError(null);
        try {
            const effectiveVoiceSpeed = kodewaves.speed;
            if (
                !Number.isFinite(effectiveVoiceSpeed)
                || effectiveVoiceSpeed < kodewavesSpeedRange.min
                || effectiveVoiceSpeed > kodewavesSpeedRange.max
            ) {
                throw new Error(
                    `Voice speed must be between ${kodewavesSpeedRange.min} and ${kodewavesSpeedRange.max}.`,
                );
            }
            const isAllLocal = kodewaves.llm_engine_type === "local_cpu" && kodewaves.stt_engine_type === "local_cpu" && kodewaves.tts_engine_type === "local_cpu";
            const apiKey = isAllLocal ? "sovereign-local-cpu" : "sovereign-managed";
            const isRt = overrideRealtime !== undefined ? overrideRealtime : Boolean(kodewaves.is_realtime);
            if (!catalogManifest || catalogError) throw new Error("Refresh the model catalog before saving.");
            if (!isRt) {
                if (kodewaves.stt_model === "indicconformer-ctc-int8" && kodewaves.language === MULTILINGUAL_LANGUAGE_CODE) {
                    throw new Error("Self-hosted STT needs a specific installed language. Select one, or switch STT to cloud for automatic language detection.");
                }
                if (!kodewaves.voice.trim()) throw new Error("Select a voice for the selected TTS model before saving.");
                for (const [label, selected, models] of [
                    ["LLM", kodewaves.llm_model, effectiveLlmModels],
                    ["STT", kodewaves.stt_model, effectiveSttModels],
                    ["TTS", kodewaves.tts_model, effectiveTtsModels],
                ] as const) {
                    if (!models.some(model => model.value === (selected || "auto"))) {
                        throw new Error(`Select an available ${label} model before saving.`);
                    }
                }
                if (!allowCustomVoice || kodewaves.tts_engine_type === "local_cpu") {
                    const voices = await getVoicesApiV1UserConfigurationsVoicesProviderGet({
                        path: { provider: effectiveTtsProvider },
                        query: {
                            model: kodewaves.tts_model || undefined,
                            q: kodewaves.voice,
                            // A local VITS voice is a preferred demo voice. Recognition
                            // language belongs to STT and must not filter this list.
                            language: kodewaves.tts_model === "indic-vits-rasa-13" || kodewaves.language === MULTILINGUAL_LANGUAGE_CODE
                                ? undefined : kodewaves.language,
                        },
                    });
                    if (voices.error) throw new Error(detailFromError(voices.error, "Unable to verify selected voice."));
                    if (!voices.data?.voices.some(voice => voice.voice_id === kodewaves.voice)) {
                        throw new Error(kodewaves.tts_model === "indic-vits-rasa-13"
                            ? "Select an installed voice for this TTS model. Recognition language is configured separately."
                            : "Select an available voice for the selected TTS model and language.");
                    }
                }
            }

            const payload = {
                api_key: apiKey,
                voice: kodewaves.voice,
                speed: effectiveVoiceSpeed,
                language: kodewaves.language,
                llm_engine_type: kodewaves.llm_engine_type,
                stt_engine_type: kodewaves.stt_engine_type,
                tts_engine_type: kodewaves.tts_engine_type,
                llm_model: kodewaves.llm_model || undefined,
                stt_model: kodewaves.stt_model || undefined,
                tts_model: kodewaves.tts_model || undefined,
                is_realtime: isRt,
                realtime_provider: kodewaves.realtime_provider || (effectiveS2sModels[0]?.provider || "google"),
                realtime_model: kodewaves.realtime_model || (effectiveS2sModels[0]?.value || undefined),
            };
            await onSave({
                version: 2,
                mode: "kodewaves",
                kodewaves: payload,
                dograh: payload,
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
                    <TabsTrigger value="kodewaves" className="gap-2">
                        <Layers className="h-4 w-4" />
                        General (STT + LLM + TTS)
                    </TabsTrigger>
                    <TabsTrigger value="realtime" className="gap-2">
                        <Sparkles className="h-4 w-4" />
                        Speech to Speech (S2S / STS)
                    </TabsTrigger>
                    <TabsTrigger value="byok" className="gap-2">
                        <Key className="h-4 w-4" />
                        BYOK (Custom Keys)
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="realtime" className="mt-0 space-y-4">
                    <p className="text-sm text-muted-foreground">
                        Speech-to-speech models stream audio directly. Response latency depends on the selected provider, model, region, and connection.
                    </p>
                    <PricingSummary pricing={pricing} includeManagedModel thirdPartyModels />
                    <Card>
                        <CardContent className="pt-6">
                            <div className="grid gap-4 sm:grid-cols-2">
                                <div className="rounded-xl border border-primary/20 bg-primary/5 p-3.5 sm:col-span-2">
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                        <div className="flex items-center gap-2">
                                            <Sparkles className="h-4 w-4 text-primary" />
                                            <span className="text-xs font-semibold text-foreground">Sovereign Speech-to-Speech (S2S / STS)</span>
                                        </div>
                                        <span className="rounded-md border border-primary/30 bg-background px-2 py-0.5 font-mono text-[11px] font-bold text-primary">
                                            Bidirectional Audio Streaming
                                        </span>
                                    </div>
                                    <p className="mt-1 text-[11px] text-muted-foreground">
                                        Powered by the platform&apos;s central master credentials (Google Gemini / OpenAI). Zero API key setup required.
                                    </p>
                                </div>

                                {/* S2S Model Selector */}
                                <div className="space-y-2 sm:col-span-2">
                                    <Label className="flex items-center gap-1.5 font-semibold text-xs text-foreground">
                                        <Bot className="h-4 w-4 text-primary" />
                                        Realtime S2S Model
                                    </Label>
                                    <Select
                                        disabled={effectiveS2sModels.length === 0}
                                        value={
                                            effectiveS2sModels.length === 0
                                                ? "none"
                                                : (kodewaves.realtime_model && effectiveS2sModels.some((m) => m.value === kodewaves.realtime_model)
                                                    ? kodewaves.realtime_model
                                                    : (effectiveS2sModels[0]?.value || "none"))
                                        }
                                        onValueChange={(val) => {
                                            const chosen = effectiveS2sModels.find((m) => m.value === val);
                                            const prov = chosen?.provider || (val.includes("gemini") ? "google" : "openai");
                                            const nextVoice = prov === "openai" ? "alloy" : "Puck";
                                            setKodewaves({
                                                ...kodewaves,
                                                realtime_model: val,
                                                realtime_provider: prov,
                                                voice: nextVoice,
                                            });
                                        }}
                                    >
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder={effectiveS2sModels.length === 0 ? "No realtime models available" : "Select Realtime Model"} />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {effectiveS2sModels.length === 0 ? (
                                                <SelectItem key="none" value="none" disabled>
                                                    No active master keys for Gemini Live or OpenAI Realtime (Configure in Admin &gt; Models)
                                                </SelectItem>
                                            ) : (
                                                effectiveS2sModels.map((m) => (
                                                    <SelectItem key={m.value} value={m.value}>
                                                        {m.label}
                                                    </SelectItem>
                                                ))
                                            )}
                                        </SelectContent>
                                    </Select>
                                    {kodewaves.realtime_model && effectiveS2sModels.length > 0 && !effectiveS2sModels.some((m) => m.value === kodewaves.realtime_model) && (
                                        <div className="flex items-center gap-1.5 text-xs text-destructive font-medium mt-1">
                                            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                                            Selected model &quot;{kodewaves.realtime_model}&quot; is no longer active in the catalog.
                                        </div>
                                    )}
                                </div>

                                {/* S2S Voice Selector */}
                                <div className="space-y-2 sm:col-span-2">
                                    <Label className="flex items-center gap-1.5 font-semibold text-xs text-foreground">
                                        <Volume2 className="h-4 w-4 text-primary" />
                                        Realtime Voice
                                    </Label>
                                    <Select
                                        value={
                                            effectiveS2sVoices.some((v) => v.value === kodewaves.voice)
                                                ? kodewaves.voice
                                                : (effectiveS2sVoices[0]?.value || "Puck")
                                        }
                                        onValueChange={(v) => setKodewaves({ ...kodewaves, voice: v })}
                                    >
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder="Select voice" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {effectiveS2sVoices.map((v) => (
                                                <SelectItem key={v.value} value={v.value}>
                                                    {v.label}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                {/* Language Selector */}
                                <div className="space-y-2 sm:col-span-2">
                                    <Label className="text-xs font-semibold">Language</Label>
                                    <Select value={kodewaves.language} onValueChange={setRecognitionLanguage}>
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
                                    {kodewaves.language === MULTILINGUAL_LANGUAGE_CODE && (
                                        <p className="text-xs text-muted-foreground">
                                            Speech recognition auto-detects only languages supported by the selected STT model. Voice output uses the selected voice and its supported language.
                                        </p>
                                    )}
                                </div>

                                <div className="sm:col-span-2 p-4 rounded-xl border border-primary/20 bg-primary/5 flex items-start gap-3">
                                    <ShieldCheck className="h-5 w-5 text-primary shrink-0 mt-0.5" />
                                    <div className="space-y-1 text-xs">
                                        <div className="font-semibold text-foreground text-sm">
                                            Sovereign Realtime Execution
                                        </div>
                                        <p className="text-muted-foreground leading-relaxed">
                                            Speech-to-Speech runs automatically using the central master credentials configured in your Admin Panel. Minutes are deducted from your balance as calls take place.
                                        </p>
                                    </div>
                                </div>
                            </div>

                            <Button
                                type="button"
                                className="mt-6 w-full"
                                onClick={() => saveKodewavesConfiguration(true)}
                                disabled={isSavingKodewaves}
                            >
                                <Save className="mr-2 h-4 w-4" />
                                {isSavingKodewaves ? "Saving..." : submitLabel || "Save Speech to Speech Configuration"}
                            </Button>
                        </CardContent>
                    </Card>

                    {/* Collapsible BYOK for Realtime */}
                    <div className="pt-2 border-t border-border/40">
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="text-xs text-muted-foreground hover:text-foreground"
                            onClick={() => setShowRealtimeByok(!showRealtimeByok)}
                        >
                            {showRealtimeByok ? "▲ Hide Custom BYOK Realtime Keys" : "▼ Need to use your own private API keys instead? Click to configure BYOK Realtime"}
                        </Button>
                        {showRealtimeByok && (
                            <div className="mt-3 p-4 rounded-xl border bg-muted/20">
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
                            </div>
                        )}
                    </div>
                </TabsContent>


                <TabsContent value="kodewaves" className="mt-0">
                    <p className="mb-4 text-sm text-muted-foreground">
                        Select cloud or local models independently for speech recognition, reasoning, and voice. Calls use the saved selections.
                    </p>
                    {catalogError && <p role="alert" className="mb-4 text-sm text-destructive">{catalogError}</p>}
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
                                        Mix and match cloud master keys and self-hosted engines independently for each layer based on your latency and cost preferences.
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
                                                onClick={() => setKodewaves({
                                                    ...kodewaves,
                                                    llm_engine_type: "cloud",
                                                    llm_model: kodewaves.llm_engine_type === "cloud" ? kodewaves.llm_model : undefined,
                                                })}
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
                                                    setKodewaves({
                                                        ...kodewaves,
                                                        llm_engine_type: "local_cpu",
                                                        llm_model: kodewaves.llm_engine_type === "local_cpu"
                                                            ? kodewaves.llm_model
                                                            : catalogManifest?.local_llm_models?.[0]?.value,
                                                    });
                                                }}
                                                className={`flex items-center gap-1 rounded-md px-2 py-0.5 font-medium transition-all ${
                                                    kodewaves.llm_engine_type === "local_cpu"
                                                        ? "bg-amber-500 text-white shadow-xs"
                                                        : "text-muted-foreground hover:text-foreground"
                                                }`}
                                            >
                                                <Cpu className="h-3 w-3" /> Self-hosted
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
                                                    : (!kodewaves.llm_model && effectiveLlmModels.some(model => model.value === "auto") ? "auto" : ""))
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
                                    {kodewaves.llm_model && effectiveLlmModels.length > 0 && !effectiveLlmModels.some((m) => m.value === kodewaves.llm_model) && (
                                        <div className="flex items-center gap-1.5 text-xs text-destructive font-medium mt-1">
                                            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                                            Selected model &quot;{kodewaves.llm_model}&quot; is no longer active in the catalog.
                                        </div>
                                    )}
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
                                                onClick={() => setKodewaves({
                                                    ...kodewaves,
                                                    stt_engine_type: "cloud",
                                                    stt_model: kodewaves.stt_engine_type === "cloud" ? kodewaves.stt_model : undefined,
                                                })}
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
                                                    setKodewaves({
                                                        ...kodewaves,
                                                        stt_engine_type: "local_cpu",
                                                        stt_model: kodewaves.stt_engine_type === "local_cpu"
                                                            ? kodewaves.stt_model
                                                            : catalogManifest?.local_stt_models?.[0]?.value,
                                                    });
                                                }}
                                                className={`flex items-center gap-1 rounded-md px-2 py-0.5 font-medium transition-all ${
                                                    kodewaves.stt_engine_type === "local_cpu"
                                                        ? "bg-amber-500 text-white shadow-xs"
                                                        : "text-muted-foreground hover:text-foreground"
                                                }`}
                                            >
                                                <Cpu className="h-3 w-3" /> Self-hosted
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
                                                    : (!kodewaves.stt_model && effectiveSttModels.some(model => model.value === "auto") ? "auto" : ""))
                                        }
                                        onValueChange={(stt_model) => {
                                            if (stt_model === "indicconformer-ctc-int8" && kodewaves.language === MULTILINGUAL_LANGUAGE_CODE) {
                                                setError("Select an installed self-hosted STT language. Automatic recognition is unavailable for this model.");
                                                return;
                                            }
                                            setKodewaves({ ...kodewaves, stt_model: stt_model === "auto" || stt_model === "none" ? undefined : stt_model });
                                            setError(null);
                                        }}
                                    >
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder={effectiveSttModels.length === 0 ? "No active transcribers available" : "Select STT model"} />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {effectiveSttModels.length === 0 ? (
                                                <SelectItem key="none" value="none" disabled>
                                                    {kodewaves.stt_engine_type === "local_cpu"
                                                        ? "Local IndicConformer STT unavailable"
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
                                    {kodewaves.stt_model && effectiveSttModels.length > 0 && !effectiveSttModels.some((m) => m.value === kodewaves.stt_model) && (
                                        <div className="flex items-center gap-1.5 text-xs text-destructive font-medium mt-1">
                                            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                                            Selected transcriber &quot;{kodewaves.stt_model}&quot; is no longer active in the catalog.
                                        </div>
                                    )}
                                    {kodewaves.stt_model === "indicconformer-ctc-int8" && kodewaves.language === MULTILINGUAL_LANGUAGE_CODE && (
                                        <p className="text-xs text-amber-600 dark:text-amber-300">
                                            Choose a specific installed language for self-hosted STT. Cloud STT supports automatic language detection.
                                        </p>
                                    )}
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
                                                onClick={() => {
                                                    setKodewaves({
                                                        ...kodewaves,
                                                        tts_engine_type: "cloud",
                                                        voice: kodewaves.tts_engine_type === "cloud" ? kodewaves.voice : "",
                                                        tts_model: kodewaves.tts_engine_type === "cloud" ? kodewaves.tts_model : undefined,
                                                    });
                                                }}
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
                                                    setKodewaves({
                                                        ...kodewaves,
                                                        tts_engine_type: "local_cpu",
                                                        voice: kodewaves.tts_engine_type === "local_cpu" ? kodewaves.voice : "",
                                                        tts_model: kodewaves.tts_engine_type === "local_cpu"
                                                            ? kodewaves.tts_model
                                                            : catalogManifest?.local_tts_models?.[0]?.value,
                                                    });
                                                }}
                                                className={`flex items-center gap-1 rounded-md px-2 py-0.5 font-medium transition-all ${
                                                    kodewaves.tts_engine_type === "local_cpu"
                                                        ? "bg-amber-500 text-white shadow-xs"
                                                        : "text-muted-foreground hover:text-foreground"
                                                }`}
                                            >
                                                <Cpu className="h-3 w-3" /> Self-hosted
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
                                                    : (!kodewaves.tts_model && effectiveTtsModels.some(model => model.value === "auto") ? "auto" : ""))
                                        }
                                        onValueChange={(tts_model) => {
                                            const nextModel = tts_model === "auto" || tts_model === "none" ? undefined : tts_model;
                                            const nextVoice = nextModel === kodewaves.tts_model ? kodewaves.voice : "";
                                            setKodewaves({
                                                ...kodewaves,
                                                tts_model: nextModel,
                                                voice: nextVoice,
                                                speed: kodewaves.speed,
                                            });
                                            setError(null);
                                        }}
                                    >
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder={effectiveTtsModels.length === 0 ? "No active synthesizers available" : "Select TTS model"} />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {effectiveTtsModels.length === 0 ? (
                                                <SelectItem key="none" value="none" disabled>
                                                    {kodewaves.tts_engine_type === "local_cpu"
                                                        ? "No self-hosted TTS models available"
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
                                    {kodewaves.tts_model && effectiveTtsModels.length > 0 && !effectiveTtsModels.some((m) => m.value === kodewaves.tts_model) && (
                                        <div className="flex items-center gap-1.5 text-xs text-destructive font-medium mt-1">
                                            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                                            Selected voice model &quot;{kodewaves.tts_model}&quot; is no longer active in the catalog.
                                        </div>
                                    )}
                                    {kodewaves.tts_engine_type === "local_cpu" && kodewaves.tts_model && effectiveTtsModels.find((model) => model.value === kodewaves.tts_model)?.languages?.length ? (
                                        <p className="text-xs text-muted-foreground">
                                            This installed voice model reports support for: {effectiveTtsModels.find((model) => model.value === kodewaves.tts_model)!.languages!.map((language) => LANGUAGE_DISPLAY_NAMES[language] || language).join(", ")}.
                                        </p>
                                    ) : null}
                                </div>

                                <div className="space-y-2 sm:col-span-2">
                                    <Label>{kodewaves.tts_engine_type === "local_cpu" && kodewaves.tts_model === "indic-vits-rasa-13" ? "Preferred voice and demo" : "Voice"}</Label>
                                    {effectiveTtsProvider === "all" ? (
                                        <p className="text-sm text-muted-foreground">Select a TTS model to choose its voices.</p>
                                    ) : <VoiceSelectorModal
                                        provider={effectiveTtsProvider}
                                        model={kodewaves.tts_model === "auto" ? undefined : kodewaves.tts_model}
                                        source={kodewaves.tts_engine_type === "local_cpu" ? "local" : "cloud"}
                                        outputLanguage={kodewaves.tts_engine_type === "local_cpu" ? undefined : kodewaves.language}
                                        value={kodewaves.voice}
                                        onChange={(voice) => setKodewaves({
                                            ...kodewaves,
                                            voice,
                                        })}
                                        allowManualInput={allowCustomVoice}
                                    />}
                                    {kodewaves.tts_engine_type === "local_cpu" && kodewaves.tts_model === "indic-vits-rasa-13" && (
                                        <div className="space-y-1 rounded-md border p-3">
                                            <p className="text-sm font-medium">TTS language: Automatic — enabled</p>
                                            <p className="text-xs text-muted-foreground">
                                                Replies use matching installed voices automatically. The preferred voice sets the demo and preferred speaker gender; it does not lock the reply language. Shared scripts use the call language context. Unsupported languages and unavailable matching voices cannot be synthesized.
                                            </p>
                                        </div>
                                    )}
                                </div>

                                <div className="space-y-2 sm:col-span-2">
                                    <Label>Recognition language (STT)</Label>
                                    <p className="text-xs text-muted-foreground">
                                        This controls how your speech is transcribed. It is separate from automatic TTS voice routing above.
                                    </p>
                                    <Select value={kodewaves.language} onValueChange={setRecognitionLanguage}>
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
                                    {kodewaves.language === MULTILINGUAL_LANGUAGE_CODE && (
                                        <p className="text-xs text-muted-foreground">
                                            Speech recognition auto-detects only languages supported by the selected STT model. Regional VITS can switch between installed voices for unambiguous reply scripts; other voice models use the selected voice.
                                        </p>
                                    )}
                                    {kodewaves.tts_engine_type === "local_cpu" && kodewaves.tts_model === "piper" && /^([a-z]{2,3})[-_][A-Z]{2}[-_]/.test(kodewaves.voice) && (
                                        <p className="text-xs text-amber-600 dark:text-amber-400">
                                            Piper voice output: {LANGUAGE_DISPLAY_NAMES[kodewaves.voice.split(/[-_]/)[0]] || kodewaves.voice.split(/[-_]/)[0]}. This voice does not gain other languages when recognition is set to multilingual.
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

                                {kodewaves.llm_engine_type === "local_cpu" && kodewaves.stt_engine_type === "local_cpu" && kodewaves.tts_engine_type === "local_cpu" ? (
                                    <div className="sm:col-span-2 p-4 rounded-xl border border-amber-500/30 bg-amber-500/10 flex items-start gap-3">
                                        <Cpu className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
                                        <div className="space-y-1 text-xs">
                                            <div className="font-semibold text-foreground text-sm flex items-center gap-2">
                                                Self-hosted Engine Active
                                                <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-600 dark:text-amber-400 font-bold uppercase tracking-wider">
                                                    Zero Cloud Keys Required
                                                </span>
                                            </div>
                                            <p className="text-muted-foreground leading-relaxed">
                                                All three selected layers run on local engines. Voice quality and response time depend on installed models and server resources. Regional VITS switches among matching installed voices for unambiguous scripts; other models use the selected voice.
                                            </p>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="sm:col-span-2 p-4 rounded-xl border border-primary/20 bg-primary/5 flex items-start gap-3">
                                        <ShieldCheck className="h-5 w-5 text-primary shrink-0 mt-0.5" />
                                        <div className="space-y-1 text-xs">
                                            <div className="font-semibold text-foreground text-sm">
                                                Selected Cloud and Local Layers
                                            </div>
                                            <p className="text-muted-foreground leading-relaxed">
                                                Cloud layers use the selected admin-provided models and keys; local layers use installed engines. Usage charges follow the call configuration and billing policy.
                                            </p>
                                        </div>
                                    </div>
                                )}
                            </div>

                            <Button type="button" className="mt-6 w-full" onClick={() => saveKodewavesConfiguration(false)} disabled={isSavingKodewaves}>
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
