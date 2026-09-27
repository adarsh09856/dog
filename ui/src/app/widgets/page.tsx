"use client";

import {
  Check,
  CheckCircle2,
  Code,
  Copy,
  Edit,
  Globe,
  Loader2,
  MessageSquare,
  Plus,
  Radio,
  RefreshCw,
  Sparkles,
  Trash2,
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
import { Textarea } from "@/components/ui/textarea";
import { WebsiteWidget, widgetsApi } from "@/lib/kodewavesApi";

export default function WidgetsPage() {
  const [widgets, setWidgets] = useState<WebsiteWidget[]>([]);
  const [loading, setLoading] = useState(true);

  // Modal
  const [modalOpen, setModalOpen] = useState(false);
  const [editingWidget, setEditingWidget] = useState<Partial<WebsiteWidget> | null>(null);
  const [saving, setSaving] = useState(false);

  // Embed Code Dialog
  const [embedCodeOpen, setEmbedCodeOpen] = useState(false);
  const [currentSnippet, setCurrentSnippet] = useState("");
  const [copied, setCopied] = useState(false);

  const fetchWidgets = async () => {
    setLoading(true);
    try {
      const data = await widgetsApi.getWidgets();
      setWidgets(data);
    } catch (err) {
      console.error("Failed to load widgets:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWidgets();
  }, []);

  const handleSaveWidget = async () => {
    if (!editingWidget || !editingWidget.name) {
      alert("Widget name is required.");
      return;
    }
    setSaving(true);
    try {
      if (editingWidget.id) {
        await widgetsApi.updateWidget(editingWidget.id, editingWidget);
      } else {
        await widgetsApi.createWidget(editingWidget);
      }
      setModalOpen(false);
      setEditingWidget(null);
      await fetchWidgets();
    } catch (err: any) {
      alert(err.message || "Failed to save widget");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteWidget = async (id: number) => {
    if (!confirm("Are you sure you want to delete this voice widget?")) return;
    try {
      await widgetsApi.deleteWidget(id);
      await fetchWidgets();
    } catch (err: any) {
      alert(err.message || "Failed to delete widget");
    }
  };

  const showEmbedCode = (w: WebsiteWidget) => {
    const origin = typeof window !== "undefined" ? window.location.origin : "https://app.kodewaves.ai";
    const snippet = `<!-- Kodewaves Sovereign Voice Widget -->
<script
  src="${origin}/widget/loader.js"
  data-widget-id="${w.id}"
  data-primary-color="${w.primary_color || "#6366f1"}"
  data-position="${w.position || "bottom-right"}"
  async>
</script>`;
    setCurrentSnippet(snippet);
    setCopied(false);
    setEmbedCodeOpen(true);
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(currentSnippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  return (
    <div className="space-y-8 p-6 md:p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Website Voice Calling Widgets</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Embed an interactive WebRTC voice button on your website for instant 1-click customer calls.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            className="gap-2"
            onClick={() => {
              setEditingWidget({
                name: "Homepage Voice Assistant",
                primary_color: "#6366f1",
                position: "bottom-right",
                welcome_message: "Hi! How can I help you today? Tap to talk with our voice AI.",
                is_active: true,
              });
              setModalOpen(true);
            }}
          >
            <Plus className="h-4 w-4" /> Create Widget
          </Button>
          <Button variant="outline" size="sm" onClick={fetchWidgets} disabled={loading} className="gap-2">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            <span>Website Embeds ({widgets.length})</span>
            <Badge variant="secondary" className="text-xs">
              WebRTC Audio Streaming
            </Badge>
          </CardTitle>
          <CardDescription>
            Visitors on your website can talk in real-time with your voice agent directly in their browser without phone tolls.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="rounded-lg overflow-hidden">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow>
                  <TableHead className="text-xs">Widget Name</TableHead>
                  <TableHead className="text-xs">Position</TableHead>
                  <TableHead className="text-xs">Color Theme</TableHead>
                  <TableHead className="text-xs">Welcome Greeting</TableHead>
                  <TableHead className="text-xs text-center">Status</TableHead>
                  <TableHead className="text-xs text-right">Embed Script</TableHead>
                  <TableHead className="text-xs text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {widgets.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-12 text-sm text-muted-foreground">
                      No website voice widgets created yet. Click &quot;Create Widget&quot; to build an embeddable assistant.
                    </TableCell>
                  </TableRow>
                ) : (
                  widgets.map((w) => (
                    <TableRow key={w.id} className="hover:bg-muted/20">
                      <TableCell className="font-semibold text-xs">{w.name}</TableCell>
                      <TableCell className="text-xs font-mono capitalize">{w.position}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span
                            className="h-4 w-4 rounded-full border border-border"
                            style={{ backgroundColor: w.primary_color }}
                          />
                          <span className="font-mono text-xs text-muted-foreground">{w.primary_color}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-xs truncate">
                        {w.welcome_message}
                      </TableCell>
                      <TableCell className="text-center">
                        {w.is_active ? (
                          <Badge className="bg-emerald-500/10 text-emerald-600 text-[10px]">
                            Live
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="text-[10px]">
                            Inactive
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs gap-1 font-mono"
                          onClick={() => showEmbedCode(w)}
                        >
                          <Code className="h-3.5 w-3.5" />
                          &lt;Embed&gt;
                        </Button>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            onClick={() => {
                              setEditingWidget(w);
                              setModalOpen(true);
                            }}
                          >
                            <Edit className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            onClick={() => handleDeleteWidget(w.id)}
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

      {/* CREATE / EDIT WIDGET MODAL */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingWidget?.id ? "Edit Website Voice Widget" : "Create Website Voice Widget"}</DialogTitle>
            <DialogDescription>
              Style the floating voice button that appears on your website.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label className="text-xs">Widget Name *</Label>
              <Input
                value={editingWidget?.name || ""}
                onChange={(e) => setEditingWidget((prev) => prev ? { ...prev, name: e.target.value } : null)}
                placeholder="Product Landing Page Voice Button"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Position on Screen</Label>
                <Select
                  value={editingWidget?.position || "bottom-right"}
                  onValueChange={(val: any) => setEditingWidget((prev) => prev ? { ...prev, position: val } : null)}
                >
                  <SelectTrigger className="text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="bottom-right">Bottom Right</SelectItem>
                    <SelectItem value="bottom-left">Bottom Left</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1">
                <Label className="text-xs">Brand Hex Color</Label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={editingWidget?.primary_color || "#6366f1"}
                    onChange={(e) => setEditingWidget((prev) => prev ? { ...prev, primary_color: e.target.value } : null)}
                    className="h-9 w-10 rounded border border-border cursor-pointer bg-transparent"
                  />
                  <Input
                    value={editingWidget?.primary_color || "#6366f1"}
                    onChange={(e) => setEditingWidget((prev) => prev ? { ...prev, primary_color: e.target.value } : null)}
                    className="font-mono text-xs"
                  />
                </div>
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Welcome Greeting Message</Label>
              <Textarea
                rows={2}
                value={editingWidget?.welcome_message || ""}
                onChange={(e) => setEditingWidget((prev) => prev ? { ...prev, welcome_message: e.target.value } : null)}
                placeholder="Hi there! Tap the mic to talk with our voice assistant in real-time."
              />
            </div>

            <div className="flex items-center justify-between pt-1">
              <Label className="text-xs">Widget Active</Label>
              <Switch
                checked={editingWidget?.is_active ?? true}
                onCheckedChange={(checked) => setEditingWidget((prev) => prev ? { ...prev, is_active: checked } : null)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={handleSaveWidget} disabled={saving}>
              Save Widget
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* GET EMBED CODE DIALOG */}
      <Dialog open={embedCodeOpen} onOpenChange={setEmbedCodeOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Embed Voice Widget</DialogTitle>
            <DialogDescription>
              Paste this HTML snippet before the closing &lt;/body&gt; tag of your website or WordPress page.
            </DialogDescription>
          </DialogHeader>

          <div className="py-2 space-y-3">
            <pre className="p-4 rounded-lg bg-muted font-mono text-xs overflow-x-auto text-foreground border border-border/60">
              {currentSnippet}
            </pre>
          </div>

          <DialogFooter className="flex justify-between items-center sm:justify-between">
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" /> Instant WebRTC connection
            </span>
            <Button onClick={handleCopy} className="gap-2">
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              {copied ? "Copied to Clipboard!" : "Copy Code"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
