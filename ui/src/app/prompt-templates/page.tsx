"use client";
import panel from "@/components/layout/PanelWorkspace.module.css";

import {
  Check,
  Copy,
  ExternalLink,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Tag,
  Trash2,
} from "lucide-react";
import { useRouter } from "next/navigation";
import React, { useCallback, useEffect, useState } from "react";

import { createWorkflowApiV1WorkflowCreateDefinitionPost } from "@/client/sdk.gen";
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
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";
import { PromptTemplate, promptTemplatesApi } from "@/lib/kodewavesApi";
import { promptTemplateWorkflow } from "@/lib/promptTemplateWorkflow";

export default function PromptTemplatesPage() {
  const { user, loading: authLoading } = useAuth();
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [category, setCategory] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<number | string | null>(null);
  const [creatingAgentId, setCreatingAgentId] = useState<number | string | null>(null);
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [editingTemplateId, setEditingTemplateId] = useState<string | number | null>(null);

  // Modal
  const [modalOpen, setModalOpen] = useState(false);
  const [newTemplate, setNewTemplate] = useState<Partial<PromptTemplate>>({
    title: "",
    category: "General",
    description: "",
    system_prompt: "",
    first_message: "",
  });
  const router = useRouter();

  const fetchTemplates = useCallback(async () => {
    if (authLoading || !user) return;
    setLoadError(null);
    setLoading(true);
    try {
      const data = await promptTemplatesApi.getTemplates();
      setTemplates(data);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Unable to load this page. Please retry.");
      console.error("Failed to load prompt templates:", err);
    } finally {
      setLoading(false);
    }
  }, [authLoading, user]);

  useEffect(() => {
    if (authLoading || !user) return;
    fetchTemplates();
  }, [authLoading, fetchTemplates, user]);

  const handleCopyPrompt = async (t: PromptTemplate) => {
    try {
      await navigator.clipboard.writeText(t.system_prompt);
      setCopiedId(t.id);
      setTimeout(() => setCopiedId(null), 2500);
    } catch {
      setLoadError("Unable to copy the prompt. Please retry.");
    }
  };

  const handleUseTemplate = async (template: PromptTemplate) => {
    if (!user || creatingAgentId !== null) return;
    setCreatingAgentId(template.id);
    setLoadError(null);
    try {
      const response = await createWorkflowApiV1WorkflowCreateDefinitionPost({ body: {
        name: template.title, workflow_definition: promptTemplateWorkflow(template),
      } });
      if (response.error || !response.data?.id) {
        throw new Error(detailFromError(response.error, "Unable to create an agent from this template."));
      }
      router.push(`/workflow/${response.data.id}?onboarding=web_call`);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Unable to create an agent from this template.");
    } finally {
      setCreatingAgentId(null);
    }
  };

  const handleCreateTemplate = async () => {
    if (savingTemplate) return;
    if (!newTemplate.title || !newTemplate.system_prompt) {
      alert("Title and system prompt are required.");
      return;
    }
    setSavingTemplate(true);
    try {
      if (editingTemplateId !== null) {
        await promptTemplatesApi.updateTemplate(editingTemplateId, newTemplate);
      } else {
        await promptTemplatesApi.createTemplate(newTemplate);
      }
      setModalOpen(false);
      setEditingTemplateId(null);
      await fetchTemplates();
    } catch (err) {
      const action = editingTemplateId !== null ? "update" : "create";
      setLoadError(err instanceof Error ? err.message : `Failed to ${action} template`);
    } finally {
      setSavingTemplate(false);
    }
  };

  const handleEditTemplate = (template: PromptTemplate) => {
    if (template.is_featured) return;
    setEditingTemplateId(template.id);
    setNewTemplate({
      title: template.title,
      category: template.category,
      description: template.description,
      system_prompt: template.system_prompt,
      first_message: template.first_message,
      recommended_tools: template.recommended_tools,
    });
    setModalOpen(true);
  };

  const handleDeleteTemplate = async (template: PromptTemplate) => {
    if (template.is_featured || !window.confirm(`Delete the “${template.title}” template? This cannot be undone.`)) return;
    setLoadError(null);
    try {
      await promptTemplatesApi.deleteTemplate(template.id);
      const remainingTemplates = templates.filter((item) => item.id !== template.id);
      setTemplates(remainingTemplates);
      if (
        category !== "all" &&
        !remainingTemplates.some(
          (item) => item.category.toLowerCase() === category.toLowerCase()
        )
      ) {
        setCategory("all");
      }
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Unable to delete the template. Please retry.");
    }
  };

  const categories = Array.from(new Set(templates.map((template) => template.category).filter(Boolean)))
    .sort((a, b) => a.localeCompare(b));

  const filteredTemplates = templates.filter((t) => {
    const matchesCategory = category === "all" || t.category.toLowerCase() === category.toLowerCase();
    const matchesSearch =
      t.title.toLowerCase().includes(search.toLowerCase()) ||
      (t.description && t.description.toLowerCase().includes(search.toLowerCase())) ||
      (t.tags && t.tags.some((tag) => tag.toLowerCase().includes(search.toLowerCase())));
    return matchesCategory && matchesSearch;
  });

  return (
    <div className="space-y-8 p-6 md:p-8 max-w-7xl mx-auto">
      {loadError && <div role="alert" className="rounded-md border border-destructive p-3 text-sm text-destructive">{loadError}</div>}
      {/* Header */}
      <header className={panel.collectionHeader}>
        <div>
          <span className={panel.eyebrow}>BUILD / PROMPTS</span><h1>Voice Prompt Templates Gallery</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Reusable prompts and greetings for your workspace’s voice agents.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            className="gap-2"
            onClick={() => {
              setEditingTemplateId(null);
              setNewTemplate({
                title: "",
                category: "Custom",
                description: "",
                system_prompt: "",
                first_message: "",
              });
              setModalOpen(true);
            }}
          >
            <Plus className="h-4 w-4" /> Add Template
          </Button>
          <Button variant="outline" size="sm" onClick={fetchTemplates} disabled={loading} className="gap-2">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </header>

      <section aria-label="Template library summary" className="grid gap-px overflow-hidden rounded-2xl border border-border bg-border sm:grid-cols-3">
        <div className="bg-card p-5"><span className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">Templates</span><p className="mt-2 text-3xl font-semibold tabular-nums">{templates.length}</p><p className="mt-1 text-xs text-muted-foreground">Reusable agent starting points</p></div>
        <div className="bg-card p-5"><span className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">Categories</span><p className="mt-2 flex items-center gap-2 text-2xl font-semibold"><Tag className="h-5 w-5 text-primary" />{new Set(templates.map((template) => template.category)).size}</p><p className="mt-1 text-xs text-muted-foreground">Browse by business use case</p></div>
        <div className="bg-card p-5"><span className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">Featured</span><p className="mt-2 text-3xl font-semibold tabular-nums">{templates.filter((template) => template.is_featured).length}</p><p className="mt-1 text-xs text-muted-foreground">Recommended starting points</p></div>
      </section>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="relative w-full sm:w-80">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search templates by industry or tags..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 h-9 text-xs"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto overflow-x-auto pb-1">
          {["all", ...categories].map((cat) => (
            <Button
              key={cat}
              variant={category === cat ? "default" : "outline"}
              size="sm"
              className="h-8 text-xs capitalize whitespace-nowrap"
              onClick={() => setCategory(cat)}
            >
              {cat}
            </Button>
          ))}
        </div>
      </div>

      {/* Templates Grid */}
      {loading ? (
        <div className="grid gap-4 md:grid-cols-2" role="status" aria-live="polite">
          <span className="sr-only">Loading prompt templates…</span>
          {[0, 1, 2, 3].map((item) => <div className="h-64 animate-pulse rounded-2xl border border-border bg-muted/40" key={item} />)}
        </div>
      ) : filteredTemplates.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border bg-card px-6 py-14 text-center">
          <p className="text-base font-semibold">No matching templates</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">Try another search or category. You can also create a custom template for your team.</p>
          <Button className="mt-5" onClick={() => { setSearch(""); setCategory("all"); }} variant="outline">Clear filters</Button>
        </div>
      ) : (
      <div className="grid gap-5 md:grid-cols-2">
        {filteredTemplates.map((t) => (
          <Card key={t.id} className="border-border/60 flex flex-col justify-between hover:border-primary/40 transition-colors">
            <CardHeader>
              <div className="flex items-center justify-between gap-2">
                <Badge variant="outline" className="text-[10px] font-semibold uppercase">
                  {t.category}
                </Badge>
                {t.is_featured && (
                  <Badge className="bg-amber-500/10 text-amber-600 border-amber-500/20 text-[10px] gap-1">
                    <Sparkles className="h-3 w-3 fill-amber-500" /> Featured
                  </Badge>
                )}
              </div>
              <CardTitle className="text-base mt-2">{t.title}</CardTitle>
              <CardDescription>{t.description}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {t.first_message && (
                <div className="p-3 rounded-lg bg-muted/40 border border-border/40 text-xs">
                  <div className="font-semibold text-muted-foreground text-[10px] uppercase mb-1">First Greeting:</div>
                  <div className="italic text-foreground">&quot;{t.first_message}&quot;</div>
                </div>
              )}

              <div className="p-3 rounded-lg bg-card border border-border/40 text-xs">
                <div className="font-semibold text-muted-foreground text-[10px] uppercase mb-1">System Instructions:</div>
                <div className="line-clamp-4 font-mono text-[11px] text-muted-foreground whitespace-pre-wrap">
                  {t.system_prompt}
                </div>
              </div>

              {t.tags && t.tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {t.tags.map((tag) => (
                    <span key={tag} className="text-[10px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-medium">
                      #{tag}
                    </span>
                  ))}
                </div>
              )}

              <div className="pt-3 border-t border-border/40 flex items-center justify-between gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="text-xs gap-1.5"
                  onClick={() => handleCopyPrompt(t)}
                >
                  {copiedId === t.id ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
                  {copiedId === t.id ? "Prompt Copied" : "Copy Prompt"}
                </Button>
                {!t.is_featured && (
                  <div className="flex items-center gap-1">
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-xs gap-1.5"
                      aria-label={`Edit ${t.title}`}
                      onClick={() => handleEditTemplate(t)}
                    >
                      <Pencil className="h-3.5 w-3.5" /> Edit
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-xs gap-1.5 text-destructive hover:text-destructive"
                      aria-label={`Delete ${t.title}`}
                      onClick={() => handleDeleteTemplate(t)}
                    >
                      <Trash2 className="h-3.5 w-3.5" /> Delete
                    </Button>
                  </div>
                )}
                <Button
                  size="sm"
                  className="text-xs gap-1.5"
                  disabled={creatingAgentId !== null}
                  onClick={() => handleUseTemplate(t)}
                >
                  {creatingAgentId === t.id ? "Creating Agent…" : "Use in Voice Studio"} <ExternalLink className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      )}

      {/* CREATE TEMPLATE MODAL */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingTemplateId !== null ? "Edit Custom Voice Template" : "Add Custom Voice Template"}</DialogTitle>
            <DialogDescription>
              Save a high-performing voice system prompt for your organization.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label className="text-xs">Template Title *</Label>
              <Input
                value={newTemplate.title || ""}
                onChange={(e) => setNewTemplate({ ...newTemplate, title: e.target.value })}
                placeholder="e.g. Inbound Restaurant Table Booking"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Category / Industry</Label>
              <Input
                value={newTemplate.category || ""}
                onChange={(e) => setNewTemplate({ ...newTemplate, category: e.target.value })}
                placeholder="e.g. Hospitality, Retail"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Description</Label>
              <Input
                value={newTemplate.description || ""}
                onChange={(e) => setNewTemplate({ ...newTemplate, description: e.target.value })}
                placeholder="Handles evening reservation inquiries and party size"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">First Spoken Greeting</Label>
              <Input
                value={newTemplate.first_message || ""}
                onChange={(e) => setNewTemplate({ ...newTemplate, first_message: e.target.value })}
                placeholder="Good evening! Thank you for calling Spice Court. Would you like to reserve a table?"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">System Prompt Instructions *</Label>
              <Textarea
                rows={6}
                value={newTemplate.system_prompt || ""}
                onChange={(e) => setNewTemplate({ ...newTemplate, system_prompt: e.target.value })}
                placeholder="You are an empathetic, concise voice agent..."
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateTemplate} disabled={savingTemplate}>{savingTemplate ? "Saving…" : editingTemplateId !== null ? "Update Template" : "Save Template"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
