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
  Play,
  RefreshCw,
  Save,
  Send,
  Server,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import React, { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { notifyBrandingChanged, useClientBranding } from "@/context/ClientBrandingContext";
import { useAuth } from "@/lib/auth";
import { adminApi, apiFetch, PlatformSettings } from "@/lib/kodewavesApi";

import admin from "../AdminWorkspace.module.css";
import IndicSttTest from "./IndicSttTest";
import styles from "./SettingsWorkspace.module.css";

const POPULAR_OLLAMA_MODELS = [
  { value: "qwen3.5:2b-q4_K_M", label: "Qwen 3.5 2B Q4 (CPU)" },
];


type OllamaModel = Awaited<ReturnType<typeof adminApi.getOllamaModels>>["models"][number];
type OllamaTestResult = Partial<Awaited<ReturnType<typeof adminApi.testOllama>>> & { success: boolean; error?: string };
function errorMessage(error: unknown, fallback = "Request failed") { return error instanceof Error ? error.message : fallback; }

export default function AdminSettingsPage() {
  const { user, loading: authLoading } = useAuth();
  const branding = useClientBranding();
  const [settings, setSettings] = useState<PlatformSettings>({
    company_name: "Kodewaves",
    tagline: "Voice agents for web and phone",
    favicon_url: "",
    font: "geist",
    logo_url: "",
    support_email: "support@kodewaves.ai",
    primary_color: branding.primary_color || "#426b57",
    allow_user_byok: false,
    enforce_wallet_balance: true,
    enable_local_ai_engine: false,
    ollama_endpoint: "http://ollama:11434",
    whisper_endpoint: "http://whisper:8000/v1",
    indic_vits_tts_endpoint: "http://indic-vits-tts:8000/v1",
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
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [brandSaving, setBrandSaving] = useState(false);
  const [brandSaved, setBrandSaved] = useState(false);

  // Ollama Model Manager state
  const [ollamaModels, setOllamaModels] = useState<OllamaModel[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [pullModelName, setPullModelName] = useState("qwen3.5:2b-q4_K_M");
  const [customPullModel, setCustomPullModel] = useState("");
  const [isPulling, setIsPulling] = useState(false);
  const [pullStatusMessage, setPullStatusMessage] = useState<string | null>(null);
  const [ollamaEndpointStatus, setOllamaEndpointStatus] = useState<string>("");

  // Ollama test state
  const [testingOllamaModel, setTestingOllamaModel] = useState<string | null>(null);
  const [ollamaTestResult, setOllamaTestResult] = useState<OllamaTestResult | null>(null);

  // Test email state
  const [testEmailRecipient, setTestEmailRecipient] = useState("");
  const [sendingTestEmail, setSendingTestEmail] = useState(false);
  const [testEmailResult, setTestEmailResult] = useState<{ success: boolean; message: string } | null>(null);

  const fetchSettings = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await adminApi.getSettings();
      if (data && Object.keys(data).length > 0) {
        setSettings((prev) => ({ ...prev, ...data }));
      }
    } catch (err) {
      setLoadError(errorMessage(err, "Unable to load platform settings. Try again before making changes."));
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
    } catch (err: unknown) {
      console.error("Failed to fetch Ollama models:", err);
      setOllamaEndpointStatus("unreachable");
    } finally {
      setLoadingModels(false);
    }
  };

  const handleTestOllama = async (modelName: string) => {
    setTestingOllamaModel(modelName);
    setOllamaTestResult(null);
    try {
      const res = await adminApi.testOllama(modelName);
      setOllamaTestResult(res);
    } catch (err: unknown) {
      setOllamaTestResult({ success: false, error: errorMessage(err, "Test failed") });
    } finally {
      setTestingOllamaModel(null);
    }
  };

  useEffect(() => {
    if (authLoading || !user) return;
    fetchSettings();
    fetchOllamaModels();
  }, [authLoading, user]);

  const handleSaveBranding = async () => {
    setBrandSaving(true);
    setBrandSaved(false);
    try {
      await apiFetch("/installation/branding", {
        method: "PUT",
        body: JSON.stringify({
          company_name: settings.company_name,
          tagline: settings.tagline || "",
          logo_url: settings.logo_url || "",
          favicon_url: settings.favicon_url || "",
          support_email: settings.support_email || "",
          primary_color: settings.primary_color || branding.primary_color || "#426b57",
          font: settings.font || "geist",
        }),
      });
      notifyBrandingChanged();
      setBrandSaved(true);
    } catch (err) {
      alert(errorMessage(err, "Unable to save branding"));
    } finally {
      setBrandSaving(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setSavedSuccess(false);
    try {
      await adminApi.saveSettings(settings);
      notifyBrandingChanged();
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 3000);
    } catch (err: unknown) {
      alert(errorMessage(err, "Failed to save settings"));
    } finally {
      setSaving(false);
    }
  };

  const handlePullModel = async () => {
    const targetModel = customPullModel.trim() || pullModelName;
    if (!targetModel) return;
    setIsPulling(true);
    setPullStatusMessage(`Downloading ${targetModel} to the self-hosted server... (this may take 1-3 minutes)`);
    try {
      await adminApi.pullOllamaModel(targetModel);
      setPullStatusMessage(`Successfully downloaded ${targetModel}!`);
      await fetchOllamaModels();
      setCustomPullModel("");
    } catch (err: unknown) {
      setPullStatusMessage(`Failed to pull model: ${errorMessage(err)}`);
    } finally {
      setIsPulling(false);
    }
  };

  const handleDeleteModel = async (modelName: string) => {
    if (!confirm(`Delete ${modelName} from the self-hosted server Ollama model store?`)) return;
    try {
      await adminApi.deleteOllamaModel(modelName);
      await fetchOllamaModels();
    } catch (err: unknown) {
      alert(`Failed to delete model: ${errorMessage(err)}`);
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
    } catch (err: unknown) {
      setTestEmailResult({ success: false, message: errorMessage(err, "Failed to send test email") });
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

  const emailConfigured = Boolean(settings.smtp_host && settings.smtp_from);
  const paymentsConfigured = Boolean(
    (settings.razorpay_key_id && settings.razorpay_key_secret) ||
    (settings.stripe_publishable_key && settings.stripe_secret_key),
  );

  if (authLoading || loading) return <div role="status" className="flex items-center gap-3 p-8 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />Loading platform settings…</div>;
  if (loadError) return <div role="alert" className="space-y-4 rounded-xl border border-destructive/30 p-8"><p className="text-sm text-destructive">{loadError}</p><Button variant="outline" onClick={() => void fetchSettings()}>Retry</Button></div>;

  return (
    <div className={`${admin.surface} ${styles.surface}`} data-area="PLATFORM / CONFIGURATION">
      {/* Header */}
      <div className={admin.hero}>
        <div>
          <span className={admin.kicker}>PLATFORM / CONFIGURATION</span>
          <h1 className={admin.title}>Platform Settings & Sovereignty</h1>
          <p className="text-sm text-muted-foreground mt-1">
            White-label Kodewaves, configure sovereign SMTP credentials, manage self-hosted server Ollama models, and set payment gateways.
          </p>
        </div>
      <div className={`${styles.heroActions} flex w-full flex-wrap items-center gap-2 sm:w-auto sm:justify-end`}>
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

      <section className={styles.snapshot} aria-label="Platform configuration overview">
        <div className={styles.snapshotBrand}>
          <span className={styles.brandMark}>{settings.company_name?.trim().slice(0, 1).toUpperCase() || "K"}</span>
          <div className="min-w-0"><p className={styles.snapshotLabel}>Platform identity</p><p className={styles.snapshotName}>{settings.company_name || "Platform name not set"}</p></div>
        </div>
        <div className={styles.snapshotItem}><Cpu size={16} aria-hidden="true" /><div><p className={styles.snapshotLabel}>Self-hosted AI</p><p className={styles.snapshotValue}>{settings.enable_local_ai_engine ? "Enabled" : "Disabled"}</p></div></div>
        <div className={styles.snapshotItem}><Mail size={16} aria-hidden="true" /><div><p className={styles.snapshotLabel}>Email dispatch</p><p className={styles.snapshotValue}>{emailConfigured ? "Configured" : "Needs setup"}</p></div></div>
        <div className={styles.snapshotItem}><CreditCard size={16} aria-hidden="true" /><div><p className={styles.snapshotLabel}>Payments</p><p className={styles.snapshotValue}>{paymentsConfigured ? "Configured" : "Needs setup"}</p></div></div>
      </section>

      <nav className={styles.sectionNav} aria-label="Platform settings sections">
        <a href="#settings-branding">Branding</a><a href="#settings-policies">Access policies</a><a href="#settings-local-ai">Local AI</a><a href="#settings-ollama">Ollama models</a><a href="#settings-tts">Indian TTS</a><a href="#settings-stt">Indian STT</a><a href="#settings-email">Email</a><a href="#settings-payments">Payments</a>
      </nav>

      <div className={`${styles.settingsGrid} grid gap-6 md:grid-cols-2`}>
        {/* BRANDING */}
        <Card id="settings-branding" className="border-border/60">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Building2 className="h-5 w-5 text-primary" />
              White-Label Branding
            </CardTitle>
            <CardDescription>
              Update the name, logo, tagline, browser icon and colors across public pages, the workspace and this admin panel.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1"><Label htmlFor="platform-tagline" className="text-xs">Tagline</Label><Input id="platform-tagline" maxLength={160} value={settings.tagline || ""} onChange={(e) => setSettings({ ...settings, tagline: e.target.value })} /></div>
            <div className="space-y-1"><Label htmlFor="platform-favicon" className="text-xs">Browser icon URL or site path</Label><Input id="platform-favicon" value={settings.favicon_url || ""} placeholder="/favicon.ico or https://example.com/icon.png" onChange={(e) => setSettings({ ...settings, favicon_url: e.target.value })} /></div>
            <div className="space-y-1"><Label htmlFor="platform-font" className="text-xs">Platform font</Label><select id="platform-font" value={settings.font || "geist"} onChange={(e) => setSettings({ ...settings, font: e.target.value as "geist" | "system" })} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"><option value="geist">Geist</option><option value="system">System</option></select></div>
            <div className="space-y-1">
              <Label htmlFor="platform-brand-name" className="text-xs">Company / Brand Name</Label>
              <Input
                id="platform-brand-name"
                maxLength={80}
                required
                value={settings.company_name}
                onChange={(e) => setSettings({ ...settings, company_name: e.target.value })}
                placeholder="e.g. Acme Voice"
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="platform-brand-logo" className="text-xs">Brand Logo URL</Label>
              <Input
                id="platform-brand-logo"
                maxLength={500}
                value={settings.logo_url || ""}
                onChange={(e) => setSettings({ ...settings, logo_url: e.target.value })}
                placeholder="https://example.com/logo.png"
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="platform-support-email" className="text-xs">Support Email Address</Label>
              <Input
                id="platform-support-email"
                type="email"
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
                  value={settings.primary_color || branding.primary_color || "#426b57"}
                  onChange={(e) => setSettings({ ...settings, primary_color: e.target.value })}
                  className="h-9 w-12 rounded border border-border cursor-pointer bg-transparent"
                />
                <Input
                  value={settings.primary_color || branding.primary_color || "#426b57"}
                  onChange={(e) => setSettings({ ...settings, primary_color: e.target.value })}
                  className="font-mono text-xs"
                />
              </div>
            </div>
            <div className="flex items-center gap-3 pt-2"><Button type="button" onClick={() => void handleSaveBranding()} disabled={brandSaving || saving}>{brandSaving ? "Saving branding…" : "Save branding"}</Button>{brandSaved && <p role="status" className="text-xs text-muted-foreground">Branding updated across the platform.</p>}</div>
          </CardContent>
        </Card>

        {/* SOVEREIGN ACCESS & POLICIES */}
        <Card id="settings-policies" className="border-border/60">
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
        <Card id="settings-local-ai" className="border-border/60 md:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base flex items-center gap-2">
                  <Cpu className="h-5 w-5 text-indigo-500" />
                  Self-Hosted AI Engine (CPU Stack)
                </CardTitle>
                <CardDescription>
                  Runs speech recognition, response generation and speech synthesis on your Kodewaves server. Available models and voices are discovered from the configured services.
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
                  <Cpu className="h-3.5 w-3.5 text-primary" />
                  Enable Sovereign Self-hosted AI Engine
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5">
                  Allows opted-in tenants to use inference on the Kodewaves server. Access can be granted per user in User Management to control server load.
                </div>
              </div>
              <Switch
                checked={settings.enable_local_ai_engine}
                onCheckedChange={(checked) => setSettings({ ...settings, enable_local_ai_engine: checked })}
              />
            </div>

            {settings.enable_local_ai_engine && (
              <div className="p-4 rounded-xl border border-primary/30 bg-primary/5 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <div>
                    <div className="text-xs font-semibold text-foreground">Self-Hosted Server Access Policy</div>
                    <div className="text-[11px] text-muted-foreground mt-0.5">
                      Choose whether all users get access automatically or only specific users assigned in User Management.
                    </div>
                  </div>
                  <Select
                    value={settings.local_ai_access_policy || "public"}
                    onValueChange={(val) => setSettings({ ...settings, local_ai_access_policy: val === "restricted" ? "restricted" : "public" })}
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
                <p className="text-[10px] text-muted-foreground">Internal Docker address for the server Ollama container; models use server CPU, RAM, and disk.</p>
              </div>

              <details className="space-y-1">
                <summary className="cursor-pointer text-xs font-medium">Additional TTS server (advanced)</summary>
                <Label className="text-xs">OpenAI-compatible TTS endpoint</Label>
                <Input
                  value={settings.whisper_endpoint || ""}
                  onChange={(e) => setSettings({ ...settings, whisper_endpoint: e.target.value })}
                  placeholder="http://tts-service:8000/v1"
                  disabled={!settings.enable_local_ai_engine}
                />
                <p className="text-[10px] text-muted-foreground">Optional additional speech server. This address does not install a model or configure speech recognition. Available models and voices come from the running server.</p>
              </details>

              <div className="space-y-1">
                <Label className="text-xs">Combined Local TTS Endpoint</Label>
                <Input
                  value={settings.indic_vits_tts_endpoint || ""}
                  onChange={(e) => setSettings({ ...settings, indic_vits_tts_endpoint: e.target.value })}
                  placeholder="http://indic-vits-tts:8000/v1"
                  disabled={!settings.enable_local_ai_engine}
                />
                <p className="text-[10px] text-muted-foreground">Shared endpoint for installed local voices. Supported languages and speakers are discovered from the running service and shown in model configuration.</p>
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
        <Card id="settings-ollama" className="border-border/60 md:col-span-2">
          <CardHeader>
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <CardTitle className="text-base flex items-center gap-2">
                  <Server className="h-5 w-5 text-indigo-500" />
                  Server Ollama Model Manager (CPU LLM Suite)
                </CardTitle>
                <CardDescription>
                  Download, manage, and inspect LLMs in the server Ollama container. Downloads consume server storage and inference uses server CPU and RAM.
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
                    : "No Ollama models are installed on this server yet. Choose a recommended model above to download one."}
                </div>
              ) : (
                <div className="border rounded-xl divide-y overflow-hidden text-xs">
                  {ollamaModels.map((m, idx) => (
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
                            <Play className="h-3.5 w-3.5 text-primary fill-primary" />
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
                    {ollamaTestResult.supports_tools && <Badge className="bg-primary/10 text-primary border-primary/20">Tools Supported</Badge>}
                  </div>
                  <div className="text-[11px] mt-1 text-muted-foreground">
                    {ollamaTestResult.message || ollamaTestResult.error || ollamaTestResult.response}
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card id="settings-tts" className="border-border/60 md:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Self-hosted Indian TTS</CardTitle>
            <CardDescription>
              Indus Pocket TTS is the active local CPU voice for Hindi, Hinglish and Indian English. Choose its installed voice from Models; unsupported languages are not presented as available.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" size="sm" asChild>
              <a href="/model-configurations">Open model configuration</a>
            </Button>
          </CardContent>
        </Card>
        {/* LOCAL INDIAN STT */}
        <Card id="settings-stt" className="border-border/60 md:col-span-2">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Mic className="h-5 w-5 text-sky-500" />
              Self-hosted Indian speech recognition
            </CardTitle>
            <CardDescription>
              Test a selected CPU IndicConformer language against WAV audio. Live calls can use automatic detection for the supported installed speech languages shown in Model Configurations.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <IndicSttTest />
          </CardContent>
        </Card>
        {/* SMTP EMAIL SETTINGS */}
        <Card id="settings-email" className="border-border/60 md:col-span-2">
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
        <Card id="settings-payments" className="border-border/60 md:col-span-2">
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
                  <CreditCard className="h-4 w-4 text-primary" />
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
