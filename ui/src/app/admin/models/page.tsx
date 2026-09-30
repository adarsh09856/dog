"use client";

import {
  AlertCircle,
  CheckCircle2,
  Cpu,
  Edit,
  Globe,
  Key,
  Layers,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import React, { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  adminApi,
  MasterCredential,
  ModelCatalogEntry,
} from "@/lib/kodewavesApi";

const DEFAULT_PROVIDERS = [
  { provider: "sarvam", name: "Sarvam AI (Indian Sovereign AI)", category: "llm", region: "India 🇮🇳" },
  { provider: "navana", name: "Navana.ai (Indic Speech AI - Hindi, Tamil, Telugu)", category: "tts", region: "India 🇮🇳" },
  { provider: "krutrim", name: "Krutrim Cloud (Indian Indic Models)", category: "llm", region: "India 🇮🇳" },
  { provider: "openai", name: "OpenAI", category: "llm", region: "Global 🌐" },
  { provider: "gemini", name: "Google Gemini", category: "llm", region: "Global 🌐" },
  { provider: "anthropic", name: "Anthropic Claude", category: "llm", region: "Global 🌐" },
  { provider: "elevenlabs", name: "ElevenLabs (TTS / Conversational)", category: "tts", region: "Global 🌐" },
  { provider: "deepgram", name: "Deepgram (STT / Aura TTS)", category: "stt", region: "Global 🌐" },
  { provider: "cartesia", name: "Cartesia Sonic", category: "tts", region: "Global 🌐" },
  { provider: "exotel", name: "Exotel (Indian Sovereign Telecom)", category: "telecom", region: "India 🇮🇳" },
  { provider: "twilio", name: "Twilio Telephony", category: "telecom", region: "Global 🌐" },
  { provider: "plivo", name: "Plivo India", category: "telecom", region: "India 🇮🇳" },
];

export default function MasterKeysAndModelsPage() {
  const [keys, setKeys] = useState<MasterCredential[]>([]);
  const [models, setModels] = useState<ModelCatalogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [testingProvider, setTestingProvider] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<string, { success: boolean; message: string; latency_ms?: number }>>({});

  // Key Edit Modal
  const [selectedKey, setSelectedKey] = useState<Partial<MasterCredential> | null>(null);
  const [keyInput, setKeyInput] = useState("");
  const [secretInput, setSecretInput] = useState("");
  const [savingKey, setSavingKey] = useState(false);

  // Model Edit / Create Modal
  const [modelModalOpen, setModelModalOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<Partial<ModelCatalogEntry> | null>(null);
  const [savingModel, setSavingModel] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [fetchedKeys, fetchedModels] = await Promise.all([
        adminApi.getMasterKeys().catch(() => []),
        adminApi.getModels().catch(() => []),
      ]);
      setKeys(fetchedKeys);
      setModels(fetchedModels);
    } catch (err) {
      console.error("Error loading master credentials & catalog:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleTestKey = async (provider: string) => {
    setTestingProvider(provider);
    try {
      const res = await adminApi.testMasterKey(provider);
      setTestResult((prev) => ({ ...prev, [provider]: res }));
    } catch (err: any) {
      setTestResult((prev) => ({
        ...prev,
        [provider]: { success: false, message: err.message || "Failed to reach provider" },
      }));
    } finally {
      setTestingProvider(null);
    }
  };

  const handleSaveKey = async () => {
    if (!selectedKey || !selectedKey.provider) return;
    setSavingKey(true);
    try {
      await adminApi.saveMasterKey({
        provider: selectedKey.provider,
        category: (selectedKey.category as any) || "llm",
        display_name: selectedKey.display_name || selectedKey.provider,
        credentials: {
          api_key: keyInput || undefined,
          api_secret: secretInput || undefined,
        },
        api_key: keyInput || undefined,
        api_secret: secretInput || undefined,
        is_active: selectedKey.is_active ?? true,
      });
      setSelectedKey(null);
      setKeyInput("");
      setSecretInput("");
      await fetchData();
    } catch (err: any) {
      alert(err.message || "Failed to save key");
    } finally {
      setSavingKey(false);
    }
  };

  const handleSaveModel = async () => {
    if (!editingModel || !editingModel.model_id) return;
    setSavingModel(true);
    try {
      if (editingModel.id) {
        await adminApi.updateModel(editingModel.id, editingModel);
      } else {
        await adminApi.createModel(editingModel);
      }
      setModelModalOpen(false);
      setEditingModel(null);
      await fetchData();
    } catch (err: any) {
      alert(err.message || "Failed to save model");
    } finally {
      setSavingModel(false);
    }
  };

  const handleDeleteModel = async (id: number) => {
    if (!confirm("Are you sure you want to remove this model from the sovereign catalog?")) return;
    try {
      await adminApi.deleteModel(id);
      await fetchData();
    } catch (err: any) {
      alert(err.message || "Failed to delete model");
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Master Credentials & AI Models</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Centrally manage sovereign API keys (Sarvam, OpenAI, ElevenLabs, Exotel) and configure markup margins.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchData} disabled={loading} className="gap-2">
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Reload
        </Button>
      </div>

      <Tabs defaultValue="credentials" className="space-y-6">
        <TabsList className="grid w-full max-w-md grid-cols-2">
          <TabsTrigger value="credentials" className="gap-2">
            <Key className="h-4 w-4" />
            Master Provider Keys
          </TabsTrigger>
          <TabsTrigger value="catalog" className="gap-2">
            <Layers className="h-4 w-4" />
            Model Catalog & Margins
          </TabsTrigger>
        </TabsList>

        {/* TAB 1: MASTER CREDENTIALS */}
        <TabsContent value="credentials" className="space-y-6">
          <Card className="border-border/60">
            <CardHeader>
              <CardTitle className="text-base flex items-center justify-between">
                <span>Platform Sovereign Master Credentials</span>
                <Badge variant="secondary" className="font-normal text-xs">
                  Encrypted AES-256 (Fernet)
                </Badge>
              </CardTitle>
              <CardDescription>
                These keys are provisioned once by Superadmin and consumed by all users unless BYOK is explicitly toggled.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {DEFAULT_PROVIDERS.map((item) => {
                  const saved = keys.find((k) => k.provider.toLowerCase() === item.provider.toLowerCase());
                  const isTested = testResult[item.provider];
                  const isTesting = testingProvider === item.provider;

                  return (
                    <div
                      key={item.provider}
                      className="flex flex-col justify-between p-4 rounded-xl border border-border/60 bg-card hover:border-primary/40 transition-colors"
                    >
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-sm">{item.name}</span>
                          <span className="text-[11px] text-muted-foreground">{item.region}</span>
                        </div>

                        <div className="flex items-center gap-2 text-xs">
                          <Badge variant="outline" className="uppercase text-[10px]">
                            {item.category}
                          </Badge>
                          {saved?.api_key_masked ? (
                            <span className="text-emerald-500 flex items-center gap-1 font-mono text-[11px]">
                              <CheckCircle2 className="h-3 w-3" />
                              {saved.api_key_masked}
                            </span>
                          ) : (
                            <span className="text-amber-500 flex items-center gap-1 text-[11px]">
                              <AlertCircle className="h-3 w-3" />
                              No Key Configured
                            </span>
                          )}
                        </div>

                        {/* Live Test Feedback */}
                        {isTested && (
                          <div
                            className={`p-2 rounded text-[11px] flex items-center gap-1.5 ${
                              isTested.success
                                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                                : "bg-destructive/10 text-destructive"
                            }`}
                          >
                            {isTested.success ? (
                              <CheckCircle2 className="h-3 w-3 shrink-0" />
                            ) : (
                              <AlertCircle className="h-3 w-3 shrink-0" />
                            )}
                            <span className="truncate">{isTested.message}</span>
                            {isTested.latency_ms && <span className="font-mono ml-auto">({isTested.latency_ms}ms)</span>}
                          </div>
                        )}
                      </div>

                      <div className="mt-4 pt-3 border-t border-border/40 flex items-center justify-between gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 text-xs gap-1"
                          onClick={() => {
                            setSelectedKey(saved || { provider: item.provider, display_name: item.name, category: item.category as any, is_active: true });
                            setKeyInput("");
                            setSecretInput("");
                          }}
                        >
                          <Edit className="h-3 w-3" />
                          {saved?.api_key_masked ? "Update Key" : "Configure Key"}
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          className="h-8 text-xs gap-1"
                          disabled={!saved?.api_key_masked || isTesting}
                          onClick={() => handleTestKey(item.provider)}
                        >
                          {isTesting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" />}
                          Test
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* TAB 2: MODEL CATALOG & MARGINS */}
        <TabsContent value="catalog" className="space-y-6">
          <Card className="border-border/60">
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-base">AI Model Catalog & Retail Pricing</CardTitle>
                <CardDescription>
                  Define which models are presented in the Studio and configure platform gross markup margins.
                </CardDescription>
              </div>
              <Button
                size="sm"
                className="gap-2"
                onClick={() => {
                  setEditingModel({
                    category: "llm",
                    is_active: true,
                    is_default: false,
                    markup_margin_percent: 50,
                    cost_per_minute: 1.0,
                    rate_per_minute: 1.5,
                  });
                  setModelModalOpen(true);
                }}
              >
                <Plus className="h-4 w-4" /> Add Catalog Entry
              </Button>
            </CardHeader>
            <CardContent>
              <div className="rounded-lg border border-border/60 overflow-hidden">
                <Table>
                  <TableHeader className="bg-muted/40">
                    <TableRow>
                      <TableHead className="text-xs">Category</TableHead>
                      <TableHead className="text-xs">Provider</TableHead>
                      <TableHead className="text-xs">Model Name</TableHead>
                      <TableHead className="text-xs">Model ID</TableHead>
                      <TableHead className="text-xs text-right">Wholesale (₹/m)</TableHead>
                      <TableHead className="text-xs text-right">Markup %</TableHead>
                      <TableHead className="text-xs text-right font-bold">Retail Rate (₹/m)</TableHead>
                      <TableHead className="text-xs text-center">Status</TableHead>
                      <TableHead className="text-xs text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {models.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={9} className="text-center py-8 text-sm text-muted-foreground">
                          No models registered in catalog yet. Click &quot;Add Catalog Entry&quot; to seed.
                        </TableCell>
                      </TableRow>
                    ) : (
                      models.map((m) => (
                        <TableRow key={m.id} className="hover:bg-muted/20">
                          <TableCell>
                            <Badge variant="outline" className="uppercase text-[10px]">
                              {m.category}
                            </Badge>
                          </TableCell>
                          <TableCell className="font-semibold text-xs capitalize">{m.provider}</TableCell>
                          <TableCell className="text-xs font-medium">{m.display_name}</TableCell>
                          <TableCell className="text-xs font-mono text-muted-foreground">{m.model_id}</TableCell>
                          <TableCell className="text-xs text-right font-mono">₹{m.cost_per_minute.toFixed(2)}</TableCell>
                          <TableCell className="text-xs text-right font-mono text-indigo-500 font-semibold">
                            +{m.markup_margin_percent}%
                          </TableCell>
                          <TableCell className="text-xs text-right font-mono font-bold text-emerald-600 dark:text-emerald-400">
                            ₹{m.rate_per_minute.toFixed(2)}
                          </TableCell>
                          <TableCell className="text-center">
                            {m.is_active ? (
                              <Badge className="bg-emerald-500/10 text-emerald-600 text-[10px] hover:bg-emerald-500/20">
                                Active
                              </Badge>
                            ) : (
                              <Badge variant="secondary" className="text-[10px]">
                                Inactive
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell className="text-right">
                            <div className="flex items-center justify-end gap-1">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7"
                                onClick={() => {
                                  setEditingModel(m);
                                  setModelModalOpen(true);
                                }}
                              >
                                <Edit className="h-3.5 w-3.5" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7 text-destructive hover:text-destructive"
                                onClick={() => handleDeleteModel(m.id)}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* MASTER KEY EDIT DIALOG */}
      <Dialog open={!!selectedKey} onOpenChange={(open) => !open && setSelectedKey(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Configure {selectedKey?.display_name || selectedKey?.provider} Key</DialogTitle>
            <DialogDescription>
              Stored with AES-256 Fernet encryption on the Kodewaves sovereign host.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label className="text-xs">API Key / Token</Label>
              <Input
                type="password"
                placeholder={selectedKey?.api_key_masked ? "Leave empty to retain existing key" : "Enter API key"}
                value={keyInput}
                onChange={(e) => setKeyInput(e.target.value)}
              />
            </div>

            {selectedKey?.provider === "exotel" || selectedKey?.provider === "twilio" ? (
              <div className="space-y-1">
                <Label className="text-xs">API Secret / Auth Token</Label>
                <Input
                  type="password"
                  placeholder="Enter API Secret"
                  value={secretInput}
                  onChange={(e) => setSecretInput(e.target.value)}
                />
              </div>
            ) : null}

            <div className="flex items-center justify-between pt-2">
              <Label className="text-xs">Enabled for platform calls</Label>
              <Switch
                checked={selectedKey?.is_active ?? true}
                onCheckedChange={(checked) => setSelectedKey((prev) => prev ? { ...prev, is_active: checked } : null)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setSelectedKey(null)} disabled={savingKey}>
              Cancel
            </Button>
            <Button onClick={handleSaveKey} disabled={savingKey}>
              {savingKey && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save Credential
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* MODEL CATALOG DIALOG */}
      <Dialog open={modelModalOpen} onOpenChange={setModelModalOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingModel?.id ? "Edit Model Catalog Entry" : "Add Model to Catalog"}</DialogTitle>
            <DialogDescription>
              Configure wholesale cost, profit markup percentage, and display name.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-2 sm:grid-cols-2">
            <div className="space-y-1">
              <Label className="text-xs">Category</Label>
              <Select
                value={editingModel?.category || "llm"}
                onValueChange={(val: any) => setEditingModel((prev) => prev ? { ...prev, category: val } : null)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="llm">LLM (Language Model)</SelectItem>
                  <SelectItem value="stt">STT (Speech-to-Text)</SelectItem>
                  <SelectItem value="tts">TTS (Text-to-Speech)</SelectItem>
                  <SelectItem value="sts">STS (Speech-to-Speech Realtime)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Provider</Label>
              <Input
                placeholder="e.g. sarvam, openai, elevenlabs"
                value={editingModel?.provider || ""}
                onChange={(e) => setEditingModel((prev) => prev ? { ...prev, provider: e.target.value } : null)}
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Display Name</Label>
              <Input
                placeholder="e.g. Sarvam 2B Indic Voice"
                value={editingModel?.display_name || ""}
                onChange={(e) => setEditingModel((prev) => prev ? { ...prev, display_name: e.target.value } : null)}
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Provider Model ID</Label>
              <Input
                placeholder="e.g. sarvam-2b-v0.5, gpt-4o-mini"
                value={editingModel?.model_id || ""}
                onChange={(e) => setEditingModel((prev) => prev ? { ...prev, model_id: e.target.value } : null)}
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Wholesale Cost (₹/min)</Label>
              <Input
                type="number"
                step="0.01"
                value={editingModel?.cost_per_minute ?? 1.0}
                onChange={(e) => {
                  const cost = parseFloat(e.target.value) || 0;
                  const markup = editingModel?.markup_margin_percent ?? 50;
                  const rate = cost * (1 + markup / 100);
                  setEditingModel((prev) => prev ? { ...prev, cost_per_minute: cost, rate_per_minute: rate } : null);
                }}
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Markup Profit (%)</Label>
              <Input
                type="number"
                value={editingModel?.markup_margin_percent ?? 50}
                onChange={(e) => {
                  const markup = parseFloat(e.target.value) || 0;
                  const cost = editingModel?.cost_per_minute ?? 1.0;
                  const rate = cost * (1 + markup / 100);
                  setEditingModel((prev) => prev ? { ...prev, markup_margin_percent: markup, rate_per_minute: rate } : null);
                }}
              />
            </div>

            <div className="col-span-2 p-3 bg-muted/40 rounded-lg flex items-center justify-between text-xs">
              <span className="font-semibold text-muted-foreground">Calculated Retail Rate:</span>
              <span className="text-base font-bold text-emerald-600 dark:text-emerald-400 font-mono">
                ₹{editingModel?.rate_per_minute?.toFixed(2) ?? "1.50"} / minute
              </span>
            </div>

            <div className="col-span-2 flex items-center justify-between pt-2">
              <Label className="text-xs">Active in Studio Catalog</Label>
              <Switch
                checked={editingModel?.is_active ?? true}
                onCheckedChange={(checked) => setEditingModel((prev) => prev ? { ...prev, is_active: checked } : null)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setModelModalOpen(false)} disabled={savingModel}>
              Cancel
            </Button>
            <Button onClick={handleSaveModel} disabled={savingModel}>
              {savingModel && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save Model
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
