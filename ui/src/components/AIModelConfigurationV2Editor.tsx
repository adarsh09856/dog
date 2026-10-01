"use client";

import { Bot, CheckCircle2, Cloud, Cpu, Info, Mic, Save, ShieldCheck, Sparkles } from "lucide-react";
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
    llm_model?: string;
    stt_model?: string;
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
    { value: "qwen2.5:0.5b", label: "Qwen 2.5 0.5B (Ultra-fast CPU, ~350MB RAM)" },
    { value: "qwen2.5:1.5b", label: "Qwen 2.5 1.5B (Recommended CPU, ~980MB RAM)" },
    { value: "llama3.2:1b", label: "Llama 3.2 1B (Meta fast CPU, ~1.3GB RAM)" },
    { value: "llama3.2:3b", label: "Llama 3.2 3B (Meta high-IQ CPU, ~2.0GB RAM)" },
    { value: "phi4-mini", label: "Microsoft Phi-4 Mini 3.8B (~2.4GB RAM)" },
    { value: "mistral:7b", label: "Mistral 7B (~4.5GB RAM)" },
];

export const CLOUD_STT_MODELS = [
    { value: "auto", label: "Auto (Recommended - Nova-3 / Whisper)" },
    { value: "deepgram-nova-3", label: "Deepgram Nova-3 (Highest Accuracy & Speed)" },
    { value: "whisper-1", label: "OpenAI Whisper-1 (Accurate Multilingual)" },
    { value: "saaras:v2", label: "Sarvam Saaras v2 (High-accuracy Indic Speech)" },
    { value: "azure-stt", label: "Microsoft Azure Speech" },
];

export const LOCAL_STT_MODELS = [
    { value: "Systran/faster-whisper-tiny.en", label: "Whisper Tiny English (Fastest CPU)" },
    { value: "Systran/faster-whisper-base", label: "Whisper Base Multilingual (Recommended CPU)" },
    { value: "Systran/faster-whisper-small", label: "Whisper Small Multilingual (High Accuracy CPU)" },
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
    if (configuredKodewaves) {
        const apiKey = String(configuredKodewaves.api_key || "");
        const isLocalCpu = apiKey === "sovereign-local-cpu" || apiKey.includes("local-cpu") || apiKey.endsWith("-cpu");
        return {
            api_key: apiKey,
            voice: String(configuredKodewaves.voice || fallback.voice),
            speed: numberOrDefault(configuredKodewaves.speed, fallback.speed),
            language: String(configuredKodewaves.language || fallback.language),
            engine_type: isLocalCpu ? "local_cpu" : "cloud",
            llm_model: configuredKodewaves.llm_model ? String(configuredKodewaves.llm_model) : undefined,
            stt_model: configuredKodewaves.stt_model ? String(configuredKodewaves.stt_model) : undefined,
        };
    }

    if (isKodewavesEffectiveConfig(effectiveConfiguration)) {
        const llm = asRecord(effectiveConfiguration?.llm);
        const tts = asRecord(effectiveConfiguration?.tts);
        const stt = asRecord(effectiveConfiguration?.stt);
        const apiKey = firstApiKey(llm?.api_key || tts?.api_key || stt?.api_key);
        const isLocalCpu = apiKey === "sovereign-local-cpu" || apiKey.includes("local-cpu") || apiKey.endsWith("-cpu") || llm?.provider === "speaches";
        return {
            api_key: apiKey,
            voice: String(tts?.voice || fallback.voice),
            speed: numberOrDefault(tts?.speed, fallback.speed),
            language: String(stt?.language || fallback.language),
            engine_type: isLocalCpu ? "local_cpu" : "cloud",
            llm_model: llm?.model ? String(llm.model) : undefined,
            stt_model: stt?.model ? String(stt.model) : undefined,
        };
    }

    return {
        api_key: "",
        voice: fallback.voice,
        speed: fallback.speed,
        language: fallback.language,
        engine_type: "cloud",
        llm_model: undefined,
        stt_model: undefined,
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
            const apiKey = kodewaves.engine_type === "local_cpu" ? "sovereign-local-cpu" : "sovereign-managed";
            await onSave({
                version: 2,
                mode: "kodewaves",
                kodewaves: {
                    api_key: apiKey,
                    voice: kodewaves.voice,
                    speed: kodewaves.speed,
                    language: kodewaves.language,
                    llm_model: kodewaves.llm_model || undefined,
                    stt_model: kodewaves.stt_model || undefined,
                },
                dograh: {
                    api_key: apiKey,
                    voice: kodewaves.voice,
                    speed: kodewaves.speed,
                    language: kodewaves.language,
                    llm_model: kodewaves.llm_model || undefined,
                    stt_model: kodewaves.stt_model || undefined,
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
                                {/* AI Engine Infrastructure Selector */}
                                <div className="space-y-2 sm:col-span-2">
                                    <Label className="text-xs font-semibold text-foreground">AI Engine Infrastructure</Label>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                        <div
                                            onClick={() => setKodewaves({ ...kodewaves, engine_type: "cloud" })}
                                            className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                                                kodewaves.engine_type !== "local_cpu"
                                                    ? "border-primary bg-primary/10 shadow-sm"
                                                    : "border-border hover:border-muted-foreground/40 bg-card/50"
                                            }`}
                                        >
                                            <div className="flex items-center justify-between mb-1.5">
                                                <div className="flex items-center gap-2 font-semibold text-xs text-foreground">
                                                    <Cloud className="h-4 w-4 text-primary" />
                                                    Platform Cloud Master Keys
                                                </div>
                                                {kodewaves.engine_type !== "local_cpu" && (
                                                    <CheckCircle2 className="h-4 w-4 text-primary" />
                                                )}
                                            </div>
                                            <p className="text-[11px] text-muted-foreground leading-snug">
                                                OpenAI, Deepgram, ElevenLabs & Cartesia configured by your platform administrator. Billed in minutes from balance.
                                            </p>
                                        </div>

                                        <div
                                            onClick={() => setKodewaves({ ...kodewaves, engine_type: "local_cpu", voice: (kodewaves.voice.startsWith("dg_") || kodewaves.voice.startsWith("kw_")) ? "af_heart" : kodewaves.voice })}
                                            className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                                                kodewaves.engine_type === "local_cpu"
                                                    ? "border-amber-500 bg-amber-500/10 shadow-sm"
                                                    : "border-border hover:border-muted-foreground/40 bg-card/50"
                                            }`}
                                        >
                                            <div className="flex items-center justify-between mb-1.5">
                                                <div className="flex items-center gap-2 font-semibold text-xs text-foreground">
                                                    <Cpu className="h-4 w-4 text-amber-500" />
                                                    Sovereign Local CPU Stack
                                                </div>
                                                {kodewaves.engine_type === "local_cpu" && (
                                                    <CheckCircle2 className="h-4 w-4 text-amber-500" />
                                                )}
                                            </div>
                                            <p className="text-[11px] text-muted-foreground leading-snug">
                                                100% Free & Self-Hosted. Runs local Ollama (Qwen2.5) + Speaches Whisper STT + Kokoro TTS on host CPU.
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                {/* LLM Model Selector */}
                                <div className="space-y-2 sm:col-span-2">
                                    <div className="flex items-center justify-between">
                                        <Label className="flex items-center gap-1.5 font-semibold text-xs text-foreground">
                                            <Bot className="h-4 w-4 text-primary" />
                                            LLM Model (Intelligence Engine)
                                        </Label>
                                        <span className="text-[10px] text-muted-foreground uppercase font-semibold">
                                            {kodewaves.engine_type === "local_cpu" ? "Local Ollama" : "Cloud Master Keys"}
                                        </span>
                                    </div>
                                    <Select
                                        value={kodewaves.llm_model || (kodewaves.engine_type === "local_cpu" ? "qwen2.5:1.5b" : "auto")}
                                        onValueChange={(llm_model) => setKodewaves({ ...kodewaves, llm_model: llm_model === "auto" ? undefined : llm_model })}
                                    >
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder="Select LLM model" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {(kodewaves.engine_type === "local_cpu" ? LOCAL_LLM_MODELS : CLOUD_LLM_MODELS).map((m) => (
                                                <SelectItem key={m.value} value={m.value}>
                                                    {m.label}
                                                </SelectItem>
                                            ))}
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
                                        <span className="text-[10px] text-muted-foreground uppercase font-semibold">
                                            {kodewaves.engine_type === "local_cpu" ? "Local Whisper" : "Cloud Transcriber"}
                                        </span>
                                    </div>
                                    <Select
                                        value={kodewaves.stt_model || (kodewaves.engine_type === "local_cpu" ? "Systran/faster-whisper-base" : "auto")}
                                        onValueChange={(stt_model) => setKodewaves({ ...kodewaves, stt_model: stt_model === "auto" ? undefined : stt_model })}
                                    >
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder="Select STT model" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {(kodewaves.engine_type === "local_cpu" ? LOCAL_STT_MODELS : CLOUD_STT_MODELS).map((m) => (
                                                <SelectItem key={m.value} value={m.value}>
                                                    {m.label}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-2 sm:col-span-2">
                                    <Label>Voice</Label>
                                    <VoiceSelectorModal
                                        provider={kodewaves.engine_type === "local_cpu" ? "speaches" : "kodewaves"}
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
                                                Voice pipeline calls run exclusively on your server CPU via Ollama (Qwen2.5) and Speaches (Whisper STT & Kokoro TTS). Completely sovereign, reliable, and consumes zero wallet minutes.
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
                                                Voice pipelines run seamlessly using the master provider keys configured in your Admin Panel (OpenAI, Deepgram, Sarvam, Cartesia, ElevenLabs). Voice usage is billed in minutes from your organization balance.
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
