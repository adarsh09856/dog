"use client";

import {
  Building2,
  CheckCircle2,
  Cpu,
  KeyRound,
  Loader2,
  Mail,
  Palette,
  RefreshCw,
  Save,
  ShieldCheck,
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
    local_ai_max_concurrency: 2,
    smtp_host: "",
    smtp_port: 587,
    smtp_user: "",
    smtp_from: "noreply@kodewaves.ai",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);

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

  useEffect(() => {
    fetchSettings();
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

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Platform Settings & White-Labeling</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Customize branding to Kodewaves, configure sovereign SMTP credentials, and toggle global BYOK policies.
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
                  Host ultra-lightweight LLM, STT, and TTS directly on your VPS (Ollama + Speaches/Whisper/Kokoro) with zero third-party cloud bills.
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

            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-1">
                <Label className="text-xs">Ollama LLM Endpoint</Label>
                <Input
                  value={settings.ollama_endpoint || ""}
                  onChange={(e) => setSettings({ ...settings, ollama_endpoint: e.target.value })}
                  placeholder="http://ollama:11434"
                  disabled={!settings.enable_local_ai_engine}
                />
                <p className="text-[10px] text-muted-foreground">Default internal Docker URL for Qwen2.5-1.5B or Phi-4-mini</p>
              </div>

              <div className="space-y-1">
                <Label className="text-xs">Speaches STT/TTS Endpoint</Label>
                <Input
                  value={settings.speaches_endpoint || ""}
                  onChange={(e) => setSettings({ ...settings, speaches_endpoint: e.target.value })}
                  placeholder="http://speaches:8000/v1"
                  disabled={!settings.enable_local_ai_engine}
                />
                <p className="text-[10px] text-muted-foreground">OpenAI-compatible endpoint for faster-whisper-tiny & Kokoro-82M</p>
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

        {/* SMTP EMAIL SETTINGS */}
        <Card className="border-border/60 md:col-span-2">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Mail className="h-5 w-5 text-amber-500" />
              SMTP Email Dispatch Credentials
            </CardTitle>
            <CardDescription>
              Used for sending appointment booking confirmations, system alerts, and notification emails.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
                <Label className="text-xs">From Email Address</Label>
                <Input
                  value={settings.smtp_from || ""}
                  onChange={(e) => setSettings({ ...settings, smtp_from: e.target.value })}
                  placeholder="notifications@kodewaves.ai"
                />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
