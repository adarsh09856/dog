"use client";

import {
  Building2,
  CheckCircle2,
  Cpu,
  CreditCard,
  Download,
  HardDrive,
  KeyRound,
  Loader2,
  Mail,
  Mic,
  Palette,
  Play,
  RefreshCw,
  Save,
  Send,
  Server,
  ShieldCheck,
  Square,
  Trash2,
  Volume2,
} from "lucide-react";
import React, { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { adminApi, PlatformSettings } from "@/lib/kodewavesApi";

const POPULAR_OLLAMA_MODELS = [
  { value: "qwen2.5:0.5b", label: "Qwen 2.5 0.5B (~350 MB - Ultra Fast CPU)" },
  { value: "qwen2.5:1.5b", label: "Qwen 2.5 1.5B (~980 MB - Recommended CPU)" },
  { value: "llama3.2:1b", label: "Llama 3.2 1B (~1.3 GB - Fast Meta Model)" },
  { value: "llama3.2:3b", label: "Llama 3.2 3B (~2.0 GB - Smart Meta Model)" },
  { value: "phi4-mini", label: "Microsoft Phi-4 Mini (~2.4 GB - High IQ)" },
  { value: "mistral:7b", label: "Mistral 7B (~4.5 GB - Advanced)" },
];

const POPULAR_PIPER_VOICES = [
  { value: "hi_IN-priyamvada-medium", label: "Hindi Female: Priyamvada (Warm & Expressive)" },
  { value: "hi_IN-pratham-medium", label: "Hindi Male: Pratham (Conversational & Clear)" },
  { value: "en_US-lessac-medium", label: "English (US) Female: Lessac (Fluent & Clear)" },
  { value: "en_US-amy-medium", label: "English (US) Female: Amy (Expressive & Friendly)" },
  { value: "en_GB-alan-medium", label: "English (GB) Male: Alan (Formal British)" },
];

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<PlatformSettings>({
    company_name: "Kodewaves",
    logo_url: "",
    support_email: "support@kodewaves.ai",
    primary_color: "#6366f1",
    allow_user_byok: false,
    enforce_wallet_balance: true,
    enable_local_ai_engine: false,
    ollama_endpoint: "http://ollama:11434",
    piper_endpoint: "http://piper:5000",
    whisper_endpoint: "http://whisper:8000/v1",
    local_ai_max_concurrency: 2,
    smtp_host: "",
    smtp_port: 587,
    smtp_user: "",
    smtp_password: "",
    smtp_from: "noreply@kodewaves.ai",
    razorpay_key_id: "",
    razorpay_key_secret: "",
    stripe_publishable_key: "",
    stripe_secret_key: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);

  // Ollama Model Manager state
  const [ollamaModels, setOllamaModels] = useState<any[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [pullModelName, setPullModelName] = useState("qwen2.5:0.5b");
  const [customPullModel, setCustomPullModel] = useState("");
  const [isPulling, setIsPulling] = useState(false);
  const [pullStatusMessage, setPullStatusMessage] = useState<string | null>(null);
  const [ollamaEndpointStatus, setOllamaEndpointStatus] = useState<string>("");

  // Piper Voice Manager state
  const [piperVoices, setPiperVoices] = useState<any[]>([]);
  const [loadingVoices, setLoadingVoices] = useState(false);
  const [downloadVoiceName, setDownloadVoiceName] = useState("hi_IN-priyamvada-medium");
  const [customDownloadVoice, setCustomDownloadVoice] = useState("");
  const [isDownloadingVoice, setIsDownloadingVoice] = useState(false);
  const [voiceDownloadStatus, setVoiceDownloadStatus] = useState<string | null>(null);
  const [piperEndpointStatus, setPiperEndpointStatus] = useState<string>("");
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);
  const [audioElement, setAudioElement] = useState<HTMLAudioElement | null>(null);

  // Whisper STT Manager state
  const [whisperModels, setWhisperModels] = useState<any[]>([]);
  const [loadingWhisperModels, setLoadingWhisperModels] = useState(false);
  const [downloadWhisperName, setDownloadWhisperName] = useState("Systran/faster-whisper-base");
  const [isDownloadingWhisper, setIsDownloadingWhisper] = useState(false);
  const [whisperDownloadStatus, setWhisperDownloadStatus] = useState<string | null>(null);
  const [whisperEndpointStatus, setWhisperEndpointStatus] = useState<string>("");
  const [testingWhisperLang, setTestingWhisperLang] = useState("hi");
  const [isTestingWhisper, setIsTestingWhisper] = useState(false);
  const [whisperTestResult, setWhisperTestResult] = useState<any | null>(null);

  // Ollama test state
  const [testingOllamaModel, setTestingOllamaModel] = useState<string | null>(null);
  const [ollamaTestResult, setOllamaTestResult] = useState<any | null>(null);

  // Test email state
  const [testEmailRecipient, setTestEmailRecipient] = useState("");
  const [sendingTestEmail, setSendingTestEmail] = useState(false);
  const [testEmailResult, setTestEmailResult] = useState<{ success: boolean; message: string } | null>(null);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const data = await adminApi.getSettings();
      if (data && Object.keys(data).length > 0) {
        setSettings((prev) => ({ ...prev, ...data }));
      }
    } catch (err) {
      console.error("Failed to load platform settings:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchOllamaModels = async () => {
    setLoadingModels(true);
    try {
      const res = await adminApi.getOllamaModels();
      setOllamaModels(res.models || []);
      setOllamaEndpointStatus(res.status || "online");
    } catch (err: any) {
      console.error("Failed to fetch Ollama models:", err);
      setOllamaEndpointStatus("unreachable");
    } finally {
      setLoadingModels(false);
    }
  };

  const fetchPiperVoices = async () => {
    setLoadingVoices(true);
    try {
      const res = await adminApi.getPiperVoices();
      setPiperVoices(res.voices || []);
      setPiperEndpointStatus(res.status || "online");
    } catch {
      setPiperEndpointStatus("offline");
    } finally {
      setLoadingVoices(false);
    }
  };

  const handleDownloadVoice = async () => {
    const targetVoice = customDownloadVoice.trim() || downloadVoiceName;
    if (!targetVoice) return;
    setIsDownloadingVoice(true);
    setVoiceDownloadStatus(`Downloading voice ${targetVoice} to Piper container...`);
    try {
      const res = await adminApi.downloadPiperVoice(targetVoice);
      setVoiceDownloadStatus(res.message || `Successfully downloaded ${targetVoice}`);
      await fetchPiperVoices();
      setCustomDownloadVoice("");
    } catch (err: any) {
      setVoiceDownloadStatus(`Download status: ${err.message || "Queued"}`);
      await fetchPiperVoices();
    } finally {
      setIsDownloadingVoice(false);
    }
  };

  const handleToggleVoiceAudio = async (voiceId: string) => {
    if (playingVoiceId === voiceId && audioElement) {
      audioElement.pause();
      setAudioElement(null);
      setPlayingVoiceId(null);
      return;
    }
    if (audioElement) {
      audioElement.pause();
    }
    setPlayingVoiceId(voiceId);
    try {
      const res = await adminApi.testPiperVoice(voiceId);
      if (res.success && res.audio_base64) {
        const audio = new Audio(`data:audio/wav;base64,${res.audio_base64}`);
        setAudioElement(audio);
        audio.onended = () => {
          setPlayingVoiceId(null);
          setAudioElement(null);
        };
        audio.onerror = () => {
          setPlayingVoiceId(null);
          setAudioElement(null);
        };
        await audio.play();
      } else {
        alert(res.error || "Failed to synthesize test audio.");
        setPlayingVoiceId(null);
      }
    } catch (err: any) {
      alert(`Audio synthesis failed: ${err.message}`);
      setPlayingVoiceId(null);
    }
  };

  const handleDeletePiperVoice = async (voiceId: string) => {
    if (!confirm(`Are you sure you want to remove voice ${voiceId}?`)) return;
    try {
      await adminApi.deletePiperVoice(voiceId);
      await fetchPiperVoices();
    } catch (err: any) {
      alert(`Failed to remove voice: ${err.message}`);
    }
  };

  const fetchWhisperModels = async () => {
    setLoadingWhisperModels(true);
    try {
      const res = await adminApi.getWhisperModels();
      setWhisperModels(res.models || []);
      setWhisperEndpointStatus(res.status || "online");
    } catch {
      setWhisperEndpointStatus("offline");
    } finally {
      setLoadingWhisperModels(false);
    }
  };

  const handleDownloadWhisper = async () => {
    if (!downloadWhisperName) return;
    setIsDownloadingWhisper(true);
    setWhisperDownloadStatus(`Downloading Whisper model ${downloadWhisperName}...`);
    try {
      const res = await adminApi.downloadWhisperModel(downloadWhisperName);
      setWhisperDownloadStatus(res.message || `Model ${downloadWhisperName} ready`);
      await fetchWhisperModels();
    } catch (err: any) {
      setWhisperDownloadStatus(`Status: ${err.message || "Initiated"}`);
    } finally {
      setIsDownloadingWhisper(false);
    }
  };

  const handleDeleteWhisper = async (modelId: string) => {
    if (!confirm(`Are you sure you want to unload ${modelId}?`)) return;
    try {
      await adminApi.deleteWhisperModel(modelId);
      await fetchWhisperModels();
    } catch (err: any) {
      alert(`Failed to unload model: ${err.message}`);
    }
  };

  const handleTestWhisper = async () => {
    setIsTestingWhisper(true);
    setWhisperTestResult(null);
    try {
      const res = await adminApi.testWhisper(testingWhisperLang);
      setWhisperTestResult(res);
    } catch (err: any) {
      setWhisperTestResult({ success: false, error: err.message || "Test failed" });
    } finally {
      setIsTestingWhisper(false);
    }
  };

  const handleTestOllama = async (modelName: string) => {
    setTestingOllamaModel(modelName);
    setOllamaTestResult(null);
    try {
      const res = await adminApi.testOllama(modelName);
      setOllamaTestResult(res);
    } catch (err: any) {
      setOllamaTestResult({ success: false, error: err.message || "Test failed" });
    } finally {
      setTestingOllamaModel(null);
    }
  };

  useEffect(() => {
    fetchSettings();
    fetchOllamaModels();
    fetchPiperVoices();
    fetchWhisperModels();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSavedSuccess(false);
    try {
      await adminApi.saveSettings(settings);
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 3000);
    } catch (err: any) {
      alert(err.message || "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const handlePullModel = async () => {
    const targetModel = customPullModel.trim() || pullModelName;
    if (!targetModel) return;
    setIsPulling(true);
    setPullStatusMessage(`Downloading ${targetModel} into local Ollama... (this may take 1-3 minutes)`);
    try {
      await adminApi.pullOllamaModel(targetModel);
      setPullStatusMessage(`Successfully downloaded ${targetModel}!`);
      await fetchOllamaModels();
      setCustomPullModel("");
    } catch (err: any) {
      setPullStatusMessage(`Failed to pull model: ${err.message}`);
    } finally {
      setIsPulling(false);
    }
  };

  const handleDeleteModel = async (modelName: string) => {
    if (!confirm(`Are you sure you want to delete ${modelName} from local Ollama?`)) return;
    try {
      await adminApi.deleteOllamaModel(modelName);
      await fetchOllamaModels();
    } catch (err: any) {
      alert(`Failed to delete model: ${err.message}`);
    }
  };

  const handleSendTestEmail = async () => {
    if (!testEmailRecipient) {
      alert("Please enter a recipient email address.");
      return;
    }
    setSendingTestEmail(true);
    setTestEmailResult(null);
    try {
      const res = await adminApi.testEmail(testEmailRecipient);
      setTestEmailResult({ success: true, message: res.message });
    } catch (err: any) {
      setTestEmailResult({ success: false, message: err.message || "Failed to send test email" });
    } finally {
      setSendingTestEmail(false);
    }
  };

  const formatBytes = (bytes: number) => {
    if (!bytes) return "0 MB";
    const mb = bytes / (1024 * 1024);
    if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
    return `${mb.toFixed(1)} MB`;
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Platform Settings & Sovereignty</h1>
          <p className="text-sm text-muted-foreground mt-1">
            White-label Kodewaves, configure sovereign SMTP credentials, manage local Ollama models, and set payment gateways.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {savedSuccess && (
            <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-500/20 text-xs gap-1">
              <CheckCircle2 className="h-3.5 w-3.5" /> Settings Saved Successfully
            </Badge>
          )}
          <Button onClick={handleSave} disabled={saving} className="gap-2">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save Configuration
          </Button>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* BRANDING */}
        <Card className="border-border/60">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Building2 className="h-5 w-5 text-primary" />
              White-Label Branding
            </CardTitle>
            <CardDescription>
              Configure the platform identity displayed across the UI, invoices, and client widgets.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1">
              <Label className="text-xs">Company / Brand Name</Label>
              <Input
                value={settings.company_name}
                onChange={(e) => setSettings({ ...settings, company_name: e.target.value })}
                placeholder="e.g. Kodewaves"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Brand Logo URL</Label>
              <Input
                value={settings.logo_url || ""}
                onChange={(e) => setSettings({ ...settings, logo_url: e.target.value })}
                placeholder="https://example.com/logo.png"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Support Email Address</Label>
              <Input
                value={settings.support_email || ""}
                onChange={(e) => setSettings({ ...settings, support_email: e.target.value })}
                placeholder="support@kodewaves.ai"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Primary Brand Color</Label>
              <div className="flex items-center gap-3">
                <input
                  type="color"
                  value={settings.primary_color || "#6366f1"}
                  onChange={(e) => setSettings({ ...settings, primary_color: e.target.value })}
                  className="h-9 w-12 rounded border border-border cursor-pointer bg-transparent"
                />
                <Input
                  value={settings.primary_color || "#6366f1"}
                  onChange={(e) => setSettings({ ...settings, primary_color: e.target.value })}
                  className="font-mono text-xs"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* SOVEREIGN ACCESS & POLICIES */}
        <Card className="border-border/60">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-emerald-500" />
              Sovereign Platform Policies
            </CardTitle>
            <CardDescription>
              Enforce commercial boundaries, wallet balance rules, and BYOK access.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="p-4 rounded-xl border border-border/60 bg-muted/20 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs font-semibold flex items-center gap-1.5">
                    <KeyRound className="h-3.5 w-3.5 text-primary" />
                    Global BYOK Permission
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">
                    If disabled, NO tenant can use their own API keys, forcing platform minute purchases.
                  </div>
                </div>
                <Switch
                  checked={settings.allow_user_byok}
                  onCheckedChange={(checked) => setSettings({ ...settings, allow_user_byok: checked })}
                />
              </div>
            </div>

            <div className="p-4 rounded-xl border border-border/60 bg-muted/20 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs font-semibold flex items-center gap-1.5">
                    <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
                    Enforce Local Wallet Balance
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">
                    Automatically reject calls or terminate sessions when organization minutes reach 0.
                  </div>
                </div>
                <Switch
                  checked={settings.enforce_wallet_balance}
                  onCheckedChange={(checked) => setSettings({ ...settings, enforce_wallet_balance: checked })}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* LOCAL CPU AI ENGINE SETTINGS */}
        <Card className="border-border/60 md:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base flex items-center gap-2">
                  <Cpu className="h-5 w-5 text-indigo-500" />
                  Local AI Engine (Self-Hosted CPU Stack)
                </CardTitle>
                <CardDescription>
                  Host ultra-lightweight LLM and TTS directly on your VPS (Ollama CPU + Piper Neural TTS) with zero third-party cloud bills.
                </CardDescription>
              </div>
              <Badge variant={settings.enable_local_ai_engine ? "default" : "secondary"} className="text-xs">
                {settings.enable_local_ai_engine ? "Engine Active" : "Disabled Globally"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="p-4 rounded-xl border border-border/60 bg-muted/20 flex items-center justify-between">
              <div>
                <div className="text-xs font-semibold flex items-center gap-1.5">
                  <Cpu className="h-3.5 w-3.5 text-indigo-500" />
                  Enable Sovereign Local CPU AI Engine
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5">
                  Allows opted-in tenants to run local inference. Access must be granted per-user in User Management to prevent VPS overload.
                </div>
              </div>
              <Switch
                checked={settings.enable_local_ai_engine}
                onCheckedChange={(checked) => setSettings({ ...settings, enable_local_ai_engine: checked })}
              />
            </div>

            {settings.enable_local_ai_engine && (
              <div className="p-4 rounded-xl border border-indigo-500/30 bg-indigo-500/5 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <div>
                    <div className="text-xs font-semibold text-foreground">Local AI Access Policy</div>
                    <div className="text-[11px] text-muted-foreground mt-0.5">
                      Choose whether all users get access automatically or only specific users assigned in User Management.
                    </div>
                  </div>
                  <Select
                    value={settings.local_ai_access_policy || "public"}
                    onValueChange={(val: any) => setSettings({ ...settings, local_ai_access_policy: val })}
                  >
                    <SelectTrigger className="w-56 h-8 text-xs bg-background">
                      <SelectValue placeholder="Select Policy" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="public">🌐 Public Access (All Users)</SelectItem>
                      <SelectItem value="restricted">🔒 Restricted (Per-User Opt-in)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div className="space-y-1">
                <Label className="text-xs">Ollama LLM Endpoint</Label>
                <Input
                  value={settings.ollama_endpoint || ""}
                  onChange={(e) => setSettings({ ...settings, ollama_endpoint: e.target.value })}
                  placeholder="http://ollama:11434"
                  disabled={!settings.enable_local_ai_engine}
                />
                <p className="text-[10px] text-muted-foreground">Default internal Docker URL for Qwen2.5 or Phi-4-mini</p>
              </div>

              <div className="space-y-1">
                <Label className="text-xs">Piper TTS Endpoint</Label>
                <Input
                  value={settings.piper_endpoint || ""}
                  onChange={(e) => setSettings({ ...settings, piper_endpoint: e.target.value })}
                  placeholder="http://piper:5000"
                  disabled={!settings.enable_local_ai_engine}
                />
                <p className="text-[10px] text-muted-foreground">Local neural Piper ONNX TTS server (Hindi & English)</p>
              </div>

              <div className="space-y-1">
                <Label className="text-xs">Whisper STT Endpoint</Label>
                <Input
                  value={settings.whisper_endpoint || ""}
                  onChange={(e) => setSettings({ ...settings, whisper_endpoint: e.target.value })}
                  placeholder="http://whisper:8000/v1"
                  disabled={!settings.enable_local_ai_engine}
                />
                <p className="text-[10px] text-muted-foreground">Local Faster-Whisper CPU transcriber (CTranslate2 OpenAI /v1 format)</p>
              </div>

              <div className="space-y-1">
                <Label className="text-xs">Max Concurrent Local Sessions</Label>
                <Input
                  type="number"
                  min={1}
                  max={8}
                  value={settings.local_ai_max_concurrency || 2}
                  onChange={(e) => setSettings({ ...settings, local_ai_max_concurrency: parseInt(e.target.value) || 1 })}
                  disabled={!settings.enable_local_ai_engine}
                />
                <p className="text-[10px] text-muted-foreground">Recommended: 2 for 2-4GB VPS to prevent CPU starvation</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* OLLAMA MODEL MANAGER */}
        <Card className="border-border/60 md:col-span-2">
          <CardHeader>
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <CardTitle className="text-base flex items-center gap-2">
                  <Server className="h-5 w-5 text-indigo-500" />
                  Ollama Model Manager (CPU LLM Suite)
                </CardTitle>
                <CardDescription>
                  Download, manage, and inspect installed LLMs directly on your host Ollama container.
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Badge
                  variant={ollamaEndpointStatus === "online" ? "default" : "destructive"}
                  className="text-xs"
                >
                  {ollamaEndpointStatus === "online" ? "● Ollama Online" : `Ollama ${ollamaEndpointStatus}`}
                </Badge>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={fetchOllamaModels}
                  disabled={loadingModels}
                  className="h-8 gap-1.5 text-xs"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${loadingModels ? "animate-spin" : ""}`} />
                  Refresh
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Pull Model Form */}
            <div className="p-4 rounded-xl border border-border/60 bg-muted/20 space-y-3">
              <div className="text-xs font-semibold flex items-center gap-2">
                <Download className="h-4 w-4 text-primary" />
                Pull / Download New Ollama Model
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="space-y-1">
                  <Label className="text-xs">Select Recommended Model</Label>
                  <Select value={pullModelName} onValueChange={setPullModelName}>
                    <SelectTrigger className="w-full h-9 text-xs">
                      <SelectValue placeholder="Choose Model" />
                    </SelectTrigger>
                    <SelectContent>
                      {POPULAR_OLLAMA_MODELS.map((m) => (
                        <SelectItem key={m.value} value={m.value}>
                          {m.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">Or Custom Model Name</Label>
                  <Input
                    value={customPullModel}
                    onChange={(e) => setCustomPullModel(e.target.value)}
                    placeholder="e.g. gemma2:2b, mistral:7b"
                    className="h-9 text-xs"
                  />
                </div>

                <div className="flex items-end">
                  <Button
                    onClick={handlePullModel}
                    disabled={isPulling}
                    className="w-full h-9 text-xs gap-2"
                  >
                    {isPulling ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        Downloading...
                      </>
                    ) : (
                      <>
                        <Download className="h-3.5 w-3.5" />
                        Pull Model to Host
                      </>
                    )}
                  </Button>
                </div>
              </div>

              {pullStatusMessage && (
                <div className="text-xs text-primary font-medium p-2.5 rounded-lg bg-primary/10 border border-primary/20">
                  {pullStatusMessage}
                </div>
              )}
            </div>

            {/* Installed Models List */}
            <div className="space-y-2">
              <div className="text-xs font-semibold flex items-center gap-2">
                <HardDrive className="h-4 w-4 text-muted-foreground" />
                Installed Ollama Models ({ollamaModels.length})
              </div>

              {ollamaModels.length === 0 ? (
                <div className="p-6 text-center rounded-xl border border-dashed text-xs text-muted-foreground">
                  {loadingModels
                    ? "Checking Ollama models..."
                    : "No Ollama models installed yet. Pull 'qwen2.5:0.5b' or 'qwen2.5:1.5b' above to enable local AI!"}
                </div>
              ) : (
                <div className="border rounded-xl divide-y overflow-hidden text-xs">
                  {ollamaModels.map((m: any, idx: number) => (
                    <div
                      key={m.name || idx}
                      className="p-3 flex items-center justify-between hover:bg-muted/30 transition-colors"
                    >
                      <div className="space-y-0.5">
                        <div className="font-semibold text-foreground flex items-center gap-2">
                          {m.name}
                          <Badge variant="outline" className="text-[10px]">
                            {formatBytes(m.size)}
                          </Badge>
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          Modified: {m.modified_at ? new Date(m.modified_at).toLocaleString() : "Unknown"}
                          {m.details?.parameter_size ? ` • Size: ${m.details.parameter_size}` : ""}
                          {m.details?.quantization_level ? ` • Quant: ${m.details.quantization_level}` : ""}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={testingOllamaModel === m.name}
                          onClick={() => handleTestOllama(m.name)}
                          className="h-8 px-2.5 text-xs gap-1.5"
                        >
                          {testingOllamaModel === m.name ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Play className="h-3.5 w-3.5 text-indigo-500 fill-indigo-500" />
                          )}
                          Test Tools
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeleteModel(m.name)}
                          className="text-destructive hover:bg-destructive/10 h-8 px-2.5 text-xs gap-1"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {ollamaTestResult && (
                <div
                  className={`text-xs p-3 rounded-xl border mt-3 ${
                    ollamaTestResult.success
                      ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-600"
                      : "bg-destructive/10 border-destructive/20 text-destructive"
                  }`}
                >
                  <div className="font-semibold flex items-center gap-2">
                    {ollamaTestResult.success ? "✓ Ollama Test Passed" : "✕ Ollama Test Failed"}
                    {ollamaTestResult.latency_ms && <Badge variant="outline">{ollamaTestResult.latency_ms}ms</Badge>}
                    {ollamaTestResult.supports_tools && <Badge className="bg-indigo-500/10 text-indigo-600 border-indigo-500/20">Tools Supported</Badge>}
                  </div>
                  <div className="text-[11px] mt-1 text-muted-foreground">
                    {ollamaTestResult.message || ollamaTestResult.error || ollamaTestResult.response}
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* PIPER NEURAL VOICE MANAGER */}
        <Card className="border-border/60 md:col-span-2">
          <CardHeader>
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <CardTitle className="text-base flex items-center gap-2">
                  <Volume2 className="h-5 w-5 text-emerald-500" />
                  Piper Neural Voice Manager (Local TTS Suite)
                </CardTitle>
                <CardDescription>
                  Download and test local neural voice models (Hindi, English, Regional Indic) directly on your host Piper container without cloud API fees.
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Badge
                  variant={piperEndpointStatus === "online" ? "default" : "destructive"}
                  className="text-xs"
                >
                  {piperEndpointStatus === "online" ? "● Piper Online" : `Piper ${piperEndpointStatus}`}
                </Badge>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={fetchPiperVoices}
                  disabled={loadingVoices}
                  className="h-8 gap-1.5 text-xs"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${loadingVoices ? "animate-spin" : ""}`} />
                  Refresh
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Pull / Download Voice Form */}
            <div className="p-4 rounded-xl border border-border/60 bg-muted/20 space-y-3">
              <div className="text-xs font-semibold flex items-center gap-2">
                <Download className="h-4 w-4 text-primary" />
                Download New Neural Voice Model
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="space-y-1">
                  <Label className="text-xs">Select Popular Voice</Label>
                  <Select value={downloadVoiceName} onValueChange={setDownloadVoiceName}>
                    <SelectTrigger className="w-full h-9 text-xs">
                      <SelectValue placeholder="Choose Voice" />
                    </SelectTrigger>
                    <SelectContent>
                      {POPULAR_PIPER_VOICES.map((v) => (
                        <SelectItem key={v.value} value={v.value}>
                          {v.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1">
                  <Label className="text-xs">Or Custom Piper Voice ID</Label>
                  <Input
                    value={customDownloadVoice}
                    onChange={(e) => setCustomDownloadVoice(e.target.value)}
                    placeholder="e.g. hi_IN-rohit-medium, en_US-ryan-medium"
                    className="h-9 text-xs"
                  />
                </div>

                <div className="flex items-end">
                  <Button
                    onClick={handleDownloadVoice}
                    disabled={isDownloadingVoice}
                    className="w-full h-9 text-xs gap-2"
                  >
                    {isDownloadingVoice ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        Downloading...
                      </>
                    ) : (
                      <>
                        <Download className="h-3.5 w-3.5" />
                        Download Voice
                      </>
                    )}
                  </Button>
                </div>
              </div>

              {voiceDownloadStatus && (
                <div className="text-xs text-primary font-medium p-2.5 rounded-lg bg-primary/10 border border-primary/20">
                  {voiceDownloadStatus}
                </div>
              )}
            </div>

            {/* Installed Voices Table */}
            <div className="space-y-2">
              <div className="text-xs font-semibold flex items-center gap-2">
                <Volume2 className="h-4 w-4 text-muted-foreground" />
                Available & Installed Neural Voices ({piperVoices.length})
              </div>

              {piperVoices.length === 0 ? (
                <div className="p-6 text-center rounded-xl border border-dashed text-xs text-muted-foreground">
                  {loadingVoices
                    ? "Checking Piper voices..."
                    : "No Piper voices installed yet. Download 'hi_IN-priyamvada-medium' above!"}
                </div>
              ) : (
                <div className="border rounded-xl divide-y overflow-hidden text-xs">
                  {piperVoices.map((v: any, idx: number) => (
                    <div
                      key={v.id || v.name || idx}
                      className="p-3 flex items-center justify-between hover:bg-muted/30 transition-colors"
                    >
                      <div className="space-y-0.5">
                        <div className="font-semibold text-foreground flex items-center gap-2">
                          {v.id || v.name}
                          <Badge variant="outline" className="text-[10px] bg-emerald-500/10 text-emerald-600 border-emerald-500/20">
                            Ready
                          </Badge>
                          <Badge variant="secondary" className="text-[10px]">
                            {v.language || "Neural"}
                          </Badge>
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          {v.description || "Local low-latency ONNX voice"} • Quality: {v.quality || "Medium"} • Gender: {v.gender || "Neural"}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleToggleVoiceAudio(v.id || v.name)}
                          className="h-8 px-2.5 text-xs gap-1.5"
                        >
                          {playingVoiceId === (v.id || v.name) ? (
                            <>
                              <Square className="h-3 w-3 text-amber-500 fill-amber-500" />
                              Stop
                            </>
                          ) : (
                            <>
                              <Play className="h-3 w-3 text-primary fill-primary" />
                              Test Audio
                            </>
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeletePiperVoice(v.id || v.name)}
                          className="text-destructive hover:bg-destructive/10 h-8 px-2.5 text-xs gap-1"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* FASTER-WHISPER STT LOCAL MANAGER */}
        <Card className="border-border/60 md:col-span-2">
          <CardHeader>
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <CardTitle className="text-base flex items-center gap-2">
                  <Mic className="h-5 w-5 text-sky-500" />
                  Faster-Whisper STT Manager (Local Speech-to-Text Suite)
                </CardTitle>
                <CardDescription>
                  Host CTranslate2 CPU Faster-Whisper (Speaches) STT directly on your VPS with zero cloud API fees.
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Badge
                  variant={whisperEndpointStatus === "online" ? "default" : "destructive"}
                  className="text-xs"
                >
                  {whisperEndpointStatus === "online" ? "● Whisper Online" : `Whisper ${whisperEndpointStatus}`}
                </Badge>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={fetchWhisperModels}
                  disabled={loadingWhisperModels}
                  className="h-8 gap-1.5 text-xs"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${loadingWhisperModels ? "animate-spin" : ""}`} />
                  Refresh
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Download Model Form */}
            <div className="p-4 rounded-xl border border-border/60 bg-muted/20 space-y-3">
              <div className="text-xs font-semibold flex items-center gap-2">
                <Download className="h-4 w-4 text-primary" />
                Download / Preload Faster-Whisper Model
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label className="text-xs">Select Model Tier</Label>
                  <Select value={downloadWhisperName} onValueChange={setDownloadWhisperName}>
                    <SelectTrigger className="w-full h-9 text-xs">
                      <SelectValue placeholder="Choose Whisper Model" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Systran/faster-whisper-tiny">
                        Faster-Whisper Tiny (~75MB RAM - Fast CPU)
                      </SelectItem>
                      <SelectItem value="Systran/faster-whisper-base">
                        Faster-Whisper Base (~140MB RAM - Recommended Multilingual)
                      </SelectItem>
                      <SelectItem value="Systran/faster-whisper-small">
                        Faster-Whisper Small (~460MB RAM - High Accuracy)
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex items-end">
                  <Button
                    onClick={handleDownloadWhisper}
                    disabled={isDownloadingWhisper}
                    className="w-full h-9 text-xs gap-2"
                  >
                    {isDownloadingWhisper ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        Downloading Model...
                      </>
                    ) : (
                      <>
                        <Download className="h-3.5 w-3.5" />
                        Download Model to Host
                      </>
                    )}
                  </Button>
                </div>
              </div>

              {whisperDownloadStatus && (
                <div className="text-xs text-primary font-medium p-2.5 rounded-lg bg-primary/10 border border-primary/20">
                  {whisperDownloadStatus}
                </div>
              )}
            </div>

            {/* Test Transcription Section */}
            <div className="p-4 rounded-xl border border-sky-500/30 bg-sky-500/5 space-y-3">
              <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <Mic className="h-3.5 w-3.5 text-sky-500" />
                Live STT Audio Verification (Bundled Clips)
              </div>
              <div className="flex flex-col sm:flex-row gap-3">
                <div className="w-48">
                  <Select value={testingWhisperLang} onValueChange={setTestingWhisperLang}>
                    <SelectTrigger className="w-full h-9 text-xs bg-background">
                      <SelectValue placeholder="Select Language" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="hi">🇮🇳 Hindi Sample (hi_sample.wav)</SelectItem>
                      <SelectItem value="en">🇺🇸 English Sample (en_sample.wav)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <Button
                  onClick={handleTestWhisper}
                  disabled={isTestingWhisper}
                  variant="outline"
                  className="shrink-0 h-9 text-xs gap-2"
                >
                  {isTestingWhisper ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Play className="h-3.5 w-3.5 text-sky-500 fill-sky-500" />
                  )}
                  Run STT Audio Test
                </Button>
              </div>

              {whisperTestResult && (
                <div
                  className={`text-xs p-3 rounded-xl border ${
                    whisperTestResult.success
                      ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-600"
                      : "bg-destructive/10 border-destructive/20 text-destructive"
                  }`}
                >
                  <div className="font-semibold flex items-center gap-2">
                    {whisperTestResult.success ? "✓ Faster-Whisper Test Passed" : "✕ Faster-Whisper Test Failed"}
                    {whisperTestResult.latency_ms && <Badge variant="outline">{whisperTestResult.latency_ms}ms</Badge>}
                    <Badge variant="secondary" className="uppercase text-[10px]">{whisperTestResult.language}</Badge>
                  </div>
                  <div className="text-[11px] mt-1 text-foreground">
                    {whisperTestResult.transcript ? (
                      <span className="italic">"{whisperTestResult.transcript}"</span>
                    ) : (
                      whisperTestResult.error
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Installed Models List */}
            <div className="space-y-2">
              <div className="text-xs font-semibold flex items-center gap-2">
                <HardDrive className="h-4 w-4 text-muted-foreground" />
                Available & Installed Whisper Models ({whisperModels.length})
              </div>

              <div className="border rounded-xl divide-y overflow-hidden text-xs">
                {whisperModels.map((m: any, idx: number) => (
                  <div
                    key={m.id || idx}
                    className="p-3 flex items-center justify-between hover:bg-muted/30 transition-colors"
                  >
                    <div className="space-y-0.5">
                      <div className="font-semibold text-foreground flex items-center gap-2">
                        {m.name || m.id}
                        {m.installed ? (
                          <Badge variant="outline" className="text-[10px] bg-emerald-500/10 text-emerald-600 border-emerald-500/20">
                            Installed
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="text-[10px]">
                            Available
                          </Badge>
                        )}
                        <Badge variant="outline" className="text-[10px]">
                          {m.size}
                        </Badge>
                      </div>
                      <div className="text-[11px] text-muted-foreground">
                        Model ID: {m.id}
                      </div>
                    </div>

                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDeleteWhisper(m.id)}
                      className="text-destructive hover:bg-destructive/10 h-8 px-2.5 text-xs gap-1"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      Unload
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* SMTP EMAIL SETTINGS */}
        <Card className="border-border/60 md:col-span-2">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Mail className="h-5 w-5 text-amber-500" />
              SMTP Email Dispatch Credentials & Verification
            </CardTitle>
            <CardDescription>
              Configure SMTP credentials for sending user verification emails, booking alerts, and dispatch test emails.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <div className="space-y-1">
                <Label className="text-xs">SMTP Server Host</Label>
                <Input
                  value={settings.smtp_host || ""}
                  onChange={(e) => setSettings({ ...settings, smtp_host: e.target.value })}
                  placeholder="smtp.resend.com or smtp.gmail.com"
                />
              </div>

              <div className="space-y-1">
                <Label className="text-xs">SMTP Port</Label>
                <Input
                  type="number"
                  value={settings.smtp_port || 587}
                  onChange={(e) => setSettings({ ...settings, smtp_port: parseInt(e.target.value) || 587 })}
                />
              </div>

              <div className="space-y-1">
                <Label className="text-xs">SMTP Username</Label>
                <Input
                  value={settings.smtp_user || ""}
                  onChange={(e) => setSettings({ ...settings, smtp_user: e.target.value })}
                  placeholder="resend or user@domain.com"
                />
              </div>

              <div className="space-y-1">
                <Label className="text-xs">SMTP Password</Label>
                <Input
                  type="password"
                  value={settings.smtp_password || ""}
                  onChange={(e) => setSettings({ ...settings, smtp_password: e.target.value })}
                  placeholder="••••••••••••"
                />
              </div>

              <div className="space-y-1">
                <Label className="text-xs">From Email Address</Label>
                <Input
                  value={settings.smtp_from || ""}
                  onChange={(e) => setSettings({ ...settings, smtp_from: e.target.value })}
                  placeholder="notifications@kodewaves.ai"
                />
              </div>
            </div>

            {/* Test Email Section */}
            <div className="p-4 rounded-xl border border-amber-500/30 bg-amber-500/5 space-y-3">
              <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <Send className="h-3.5 w-3.5 text-amber-500" />
                Dispatch Test Verification Email
              </div>
              <div className="flex flex-col sm:flex-row gap-3">
                <Input
                  value={testEmailRecipient}
                  onChange={(e) => setTestEmailRecipient(e.target.value)}
                  placeholder="Enter email to receive test verification (e.g. your email)"
                  className="text-xs h-9"
                />
                <Button
                  onClick={handleSendTestEmail}
                  disabled={sendingTestEmail}
                  variant="outline"
                  className="shrink-0 h-9 text-xs gap-2"
                >
                  {sendingTestEmail ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                  Send Test Email
                </Button>
              </div>

              {testEmailResult && (
                <div
                  className={`text-xs p-2.5 rounded-lg border ${
                    testEmailResult.success
                      ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-600"
                      : "bg-destructive/10 border-destructive/20 text-destructive"
                  }`}
                >
                  {testEmailResult.message}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* PAYMENT GATEWAY SETTINGS */}
        <Card className="border-border/60 md:col-span-2">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <CreditCard className="h-5 w-5 text-emerald-500" />
              Payment Gateway Credentials (Razorpay & Stripe)
            </CardTitle>
            <CardDescription>
              Accept SaaS subscription payments and minute top-up credit packs in INR (Razorpay) or USD (Stripe).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="p-4 rounded-xl border border-border/60 bg-muted/20 space-y-3">
                <div className="text-xs font-semibold flex items-center gap-2">
                  <CreditCard className="h-4 w-4 text-primary" />
                  Razorpay (INR India Payments)
                </div>
                <div className="space-y-2">
                  <div className="space-y-1">
                    <Label className="text-xs">Razorpay Key ID</Label>
                    <Input
                      value={settings.razorpay_key_id || ""}
                      onChange={(e) => setSettings({ ...settings, razorpay_key_id: e.target.value })}
                      placeholder="rzp_live_..."
                      className="text-xs font-mono"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Razorpay Key Secret</Label>
                    <Input
                      type="password"
                      value={settings.razorpay_key_secret || ""}
                      onChange={(e) => setSettings({ ...settings, razorpay_key_secret: e.target.value })}
                      placeholder="••••••••••••"
                      className="text-xs font-mono"
                    />
                  </div>
                </div>
              </div>

              <div className="p-4 rounded-xl border border-border/60 bg-muted/20 space-y-3">
                <div className="text-xs font-semibold flex items-center gap-2">
                  <CreditCard className="h-4 w-4 text-indigo-500" />
                  Stripe (Global USD Payments)
                </div>
                <div className="space-y-2">
                  <div className="space-y-1">
                    <Label className="text-xs">Stripe Publishable Key</Label>
                    <Input
                      value={settings.stripe_publishable_key || ""}
                      onChange={(e) => setSettings({ ...settings, stripe_publishable_key: e.target.value })}
                      placeholder="pk_live_..."
                      className="text-xs font-mono"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Stripe Secret Key</Label>
                    <Input
                      type="password"
                      value={settings.stripe_secret_key || ""}
                      onChange={(e) => setSettings({ ...settings, stripe_secret_key: e.target.value })}
                      placeholder="sk_live_..."
                      className="text-xs font-mono"
                    />
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
