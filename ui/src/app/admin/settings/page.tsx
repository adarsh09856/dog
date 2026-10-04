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
  Palette,
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
import { adminApi, PlatformSettings } from "@/lib/kodewavesApi";

const POPULAR_OLLAMA_MODELS = [
  { value: "qwen2.5:0.5b", label: "Qwen 2.5 0.5B (~350 MB - Ultra Fast CPU)" },
  { value: "qwen2.5:1.5b", label: "Qwen 2.5 1.5B (~980 MB - Recommended CPU)" },
  { value: "llama3.2:1b", label: "Llama 3.2 1B (~1.3 GB - Fast Meta Model)" },
  { value: "llama3.2:3b", label: "Llama 3.2 3B (~2.0 GB - Smart Meta Model)" },
  { value: "phi4-mini", label: "Microsoft Phi-4 Mini (~2.4 GB - High IQ)" },
  { value: "mistral:7b", label: "Mistral 7B (~4.5 GB - Advanced)" },
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
    speaches_endpoint: "http://speaches:8000/v1",
    piper_endpoint: "http://piper:5000",
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

  useEffect(() => {
    fetchSettings();
    fetchOllamaModels();
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
                  Host ultra-lightweight LLM, STT, and TTS directly on your VPS (Ollama + Speaches/Whisper/Piper) with zero third-party cloud bills.
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

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
                <Label className="text-xs">Faster-Whisper STT Endpoint</Label>
                <Input
                  value={settings.speaches_endpoint || ""}
                  onChange={(e) => setSettings({ ...settings, speaches_endpoint: e.target.value })}
                  placeholder="http://speaches:8000/v1"
                  disabled={!settings.enable_local_ai_engine}
                />
                <p className="text-[10px] text-muted-foreground">OpenAI-compatible endpoint for faster-whisper CTranslate2</p>
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
                  ))}
                </div>
              )}
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
