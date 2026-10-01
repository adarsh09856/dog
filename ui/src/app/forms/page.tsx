"use client";

import {
  CheckCircle2,
  Code,
  Edit,
  Eye,
  FileSpreadsheet,
  FileText,
  ListPlus,
  Loader2,
  Plus,
  RefreshCw,
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
import { DynamicForm, formsApi } from "@/lib/kodewavesApi";

export default function FormsPage() {
  const [forms, setForms] = useState<DynamicForm[]>([]);
  const [loading, setLoading] = useState(true);

  // Form Builder Dialog
  const [modalOpen, setModalOpen] = useState(false);
  const [editingForm, setEditingForm] = useState<Partial<DynamicForm> | null>(null);
  const [saving, setSaving] = useState(false);

  // Submissions Modal
  const [submissionsOpen, setSubmissionsOpen] = useState(false);
  const [selectedFormTitle, setSelectedFormTitle] = useState("");
  const [submissions, setSubmissions] = useState<Array<{ id: number | string; data: Record<string, any>; created_at: string }>>([]);
  const [loadingSubs, setLoadingSubs] = useState(false);

  const fetchForms = async () => {
    setLoading(true);
    try {
      const data = await formsApi.getForms();
      setForms(data);
    } catch (err) {
      console.error("Failed to load forms:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchForms();
  }, []);

  const handleSaveForm = async () => {
    if (!editingForm || !editingForm.title || !editingForm.slug) {
      alert("Title and slug are required.");
      return;
    }
    setSaving(true);
    try {
      if (editingForm.id) {
        await formsApi.updateForm(editingForm.id, editingForm);
      } else {
        await formsApi.createForm(editingForm);
      }
      setModalOpen(false);
      setEditingForm(null);
      await fetchForms();
    } catch (err: any) {
      alert(err.message || "Failed to save form");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteForm = async (id: number | string) => {
    if (!confirm("Are you sure you want to delete this form and all its submissions?")) return;
    try {
      await formsApi.deleteForm(id);
      await fetchForms();
    } catch (err: any) {
      alert(err.message || "Failed to delete form");
    }
  };

  const handleViewSubmissions = async (form: DynamicForm) => {
    setSelectedFormTitle(form.title);
    setSubmissionsOpen(true);
    setLoadingSubs(true);
    try {
      const data = await formsApi.getSubmissions(form.id);
      setSubmissions(data);
    } catch (err) {
      console.error("Failed to load submissions:", err);
      setSubmissions([]);
    } finally {
      setLoadingSubs(false);
    }
  };

  const addField = () => {
    const fields = [...(editingForm?.fields || [])];
    fields.push({
      name: `field_${fields.length + 1}`,
      label: `Question ${fields.length + 1}`,
      type: "text",
      required: true,
    });
    setEditingForm((prev) => prev ? { ...prev, fields } : null);
  };

  const removeField = (index: number) => {
    const fields = [...(editingForm?.fields || [])];
    fields.splice(index, 1);
    setEditingForm((prev) => prev ? { ...prev, fields } : null);
  };

  return (
    <div className="space-y-8 p-6 md:p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dynamic Forms & Questionnaires</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Build conversational intake forms for voice agents to collect structured customer information.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            className="gap-2"
            onClick={() => {
              setEditingForm({
                title: "Customer Intake Survey",
                slug: "customer-intake",
                description: "Gathers requirements during the initial voice call.",
                fields: [
                  { name: "full_name", label: "Full Name", type: "text", required: true },
                  { name: "phone_number", label: "Phone Number", type: "phone", required: true },
                  { name: "budget", label: "Estimated Budget", type: "text", required: false },
                ],
                is_active: true,
              });
              setModalOpen(true);
            }}
          >
            <Plus className="h-4 w-4" /> Create Form
          </Button>
          <Button variant="outline" size="sm" onClick={fetchForms} disabled={loading} className="gap-2">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            <span>Configured Voice Intake Forms ({forms.length})</span>
            <Badge variant="secondary" className="text-xs">
              Direct Agent Tool Integration
            </Badge>
          </CardTitle>
          <CardDescription>
            Agents populate these form fields naturally over phone or WebRTC calls using function calls.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="rounded-lg overflow-hidden">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow>
                  <TableHead className="text-xs">Form Title</TableHead>
                  <TableHead className="text-xs">Slug Identifier</TableHead>
                  <TableHead className="text-xs text-center">Questions / Fields</TableHead>
                  <TableHead className="text-xs text-center">Submissions</TableHead>
                  <TableHead className="text-xs text-center">Status</TableHead>
                  <TableHead className="text-xs text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {forms.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-12 text-sm text-muted-foreground">
                      No forms created yet. Click &quot;Create Form&quot; to build an intake questionnaire.
                    </TableCell>
                  </TableRow>
                ) : (
                  forms.map((f) => (
                    <TableRow key={f.id} className="hover:bg-muted/20">
                      <TableCell className="font-semibold text-xs">{f.title}</TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">{f.slug}</TableCell>
                      <TableCell className="text-center">
                        <Badge variant="outline" className="text-[10px] font-mono">
                          {f.fields?.length || 0} fields
                        </Badge>
                      </TableCell>
                      <TableCell className="text-center">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 text-xs font-bold text-primary gap-1"
                          onClick={() => handleViewSubmissions(f)}
                        >
                          <Eye className="h-3 w-3" />
                          {f.submission_count || 0} leads
                        </Button>
                      </TableCell>
                      <TableCell className="text-center">
                        {f.is_active ? (
                          <Badge className="bg-emerald-500/10 text-emerald-600 text-[10px]">
                            Active
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="text-[10px]">
                            Disabled
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
                              setEditingForm(f);
                              setModalOpen(true);
                            }}
                          >
                            <Edit className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            onClick={() => handleDeleteForm(f.id)}
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

      {/* FORM BUILDER DIALOG */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingForm?.id ? "Edit Dynamic Form" : "Build Dynamic Intake Form"}</DialogTitle>
            <DialogDescription>
              Configure the questions your voice agent will collect from the caller.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Form Title *</Label>
                <Input
                  value={editingForm?.title || ""}
                  onChange={(e) => setEditingForm((prev) => prev ? { ...prev, title: e.target.value } : null)}
                  placeholder="Loan Application Intake"
                />
              </div>

              <div className="space-y-1">
                <Label className="text-xs">Slug Identifier *</Label>
                <Input
                  value={editingForm?.slug || ""}
                  onChange={(e) => setEditingForm((prev) => prev ? { ...prev, slug: e.target.value } : null)}
                  placeholder="loan-application"
                />
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Internal Description</Label>
              <Input
                value={editingForm?.description || ""}
                onChange={(e) => setEditingForm((prev) => prev ? { ...prev, description: e.target.value } : null)}
                placeholder="Questions asked to pre-qualify applicants"
              />
            </div>

            {/* Questions List */}
            <div className="space-y-3 pt-2">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Fields & Questions ({editingForm?.fields?.length || 0})
                </Label>
                <Button variant="outline" size="sm" className="h-7 text-xs gap-1" onClick={addField}>
                  <Plus className="h-3 w-3" /> Add Question
                </Button>
              </div>

              {editingForm?.fields?.map((field, idx) => (
                <div key={idx} className="p-3 rounded-lg border border-border/60 bg-muted/20 space-y-2">
                  <div className="grid grid-cols-12 gap-2 items-center">
                    <div className="col-span-5">
                      <Input
                        className="h-8 text-xs"
                        placeholder="Label / Prompt"
                        value={field.label}
                        onChange={(e) => {
                          const fields = [...(editingForm?.fields || [])];
                          fields[idx].label = e.target.value;
                          setEditingForm((prev) => prev ? { ...prev, fields } : null);
                        }}
                      />
                    </div>
                    <div className="col-span-3">
                      <Input
                        className="h-8 text-xs font-mono"
                        placeholder="Key (name)"
                        value={field.name}
                        onChange={(e) => {
                          const fields = [...(editingForm?.fields || [])];
                          fields[idx].name = e.target.value;
                          setEditingForm((prev) => prev ? { ...prev, fields } : null);
                        }}
                      />
                    </div>
                    <div className="col-span-3">
                      <Select
                        value={field.type}
                        onValueChange={(val: any) => {
                          const fields = [...(editingForm?.fields || [])];
                          fields[idx].type = val;
                          setEditingForm((prev) => prev ? { ...prev, fields } : null);
                        }}
                      >
                        <SelectTrigger className="h-8 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="text">Text</SelectItem>
                          <SelectItem value="phone">Phone</SelectItem>
                          <SelectItem value="email">Email</SelectItem>
                          <SelectItem value="number">Number</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="col-span-1 flex justify-end">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-destructive hover:text-destructive"
                        onClick={() => removeField(idx)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex items-center justify-between pt-2">
              <Label className="text-xs">Form Enabled</Label>
              <Switch
                checked={editingForm?.is_active ?? true}
                onCheckedChange={(checked) => setEditingForm((prev) => prev ? { ...prev, is_active: checked } : null)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={handleSaveForm} disabled={saving}>
              Save Questionnaire
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* SUBMISSIONS VIEWER DIALOG */}
      <Dialog open={submissionsOpen} onOpenChange={setSubmissionsOpen}>
        <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Submissions: {selectedFormTitle}</DialogTitle>
            <DialogDescription>
              Structured data captured during voice calls.
            </DialogDescription>
          </DialogHeader>

          <div className="py-2">
            {loadingSubs ? (
              <div className="flex justify-center p-8">
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
              </div>
            ) : submissions.length === 0 ? (
              <div className="text-center py-8 text-xs text-muted-foreground">
                No submissions received yet for this form.
              </div>
            ) : (
              <div className="space-y-3">
                {submissions.map((s) => (
                  <div key={s.id} className="p-3 rounded-lg border border-border/60 bg-muted/20 text-xs space-y-1.5">
                    <div className="text-[10px] text-muted-foreground font-mono">
                      Recorded: {new Date(s.created_at).toLocaleString()}
                    </div>
                    <pre className="p-2 rounded bg-background font-mono text-[11px] overflow-x-auto">
                      {JSON.stringify(s.data, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
