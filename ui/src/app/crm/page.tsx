"use client";

import {
  Building,
  CheckCircle2,
  Edit,
  Mail,
  MoreVertical,
  Phone,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  UserCheck,
  UserPlus,
  Users,
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Contact, crmApi, LeadStage } from "@/lib/kodewavesApi";

const DEFAULT_STAGES: LeadStage[] = [
  { id: 1, name: "New Lead", order: 1, color: "bg-blue-500" },
  { id: 2, name: "Contacted", order: 2, color: "bg-amber-500" },
  { id: 3, name: "Qualified", order: 3, color: "bg-purple-500" },
  { id: 4, name: "Negotiation", order: 4, color: "bg-indigo-500" },
  { id: 5, name: "Closed Won", order: 5, color: "bg-emerald-500" },
];

export default function CRMPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [stages, setStages] = useState<LeadStage[]>(DEFAULT_STAGES);
  const [search, setSearch] = useState("");
  const [selectedStage, setSelectedStage] = useState<string>("all");
  const [loading, setLoading] = useState(true);

  // Contact Modal
  const [modalOpen, setModalOpen] = useState(false);
  const [editingContact, setEditingContact] = useState<Partial<Contact> | null>(null);
  const [saving, setSaving] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [fetchedContacts, fetchedStages] = await Promise.all([
        crmApi.getContacts().catch(() => []),
        crmApi.getStages().catch(() => DEFAULT_STAGES),
      ]);
      setContacts(fetchedContacts);
      if (fetchedStages && fetchedStages.length > 0) {
        setStages(fetchedStages);
      }
    } catch (err) {
      console.error("Failed to load CRM data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleSaveContact = async () => {
    if (!editingContact || !editingContact.first_name || !editingContact.phone) {
      alert("Name and phone number are required.");
      return;
    }
    setSaving(true);
    try {
      if (editingContact.id) {
        await crmApi.updateContact(editingContact.id, editingContact);
      } else {
        await crmApi.createContact(editingContact);
      }
      setModalOpen(false);
      setEditingContact(null);
      await fetchData();
    } catch (err: any) {
      alert(err.message || "Failed to save contact");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteContact = async (id: number) => {
    if (!confirm("Are you sure you want to delete this contact?")) return;
    try {
      await crmApi.deleteContact(id);
      await fetchData();
    } catch (err: any) {
      alert(err.message || "Failed to delete contact");
    }
  };

  const filteredContacts = contacts.filter((c) => {
    const matchesSearch =
      c.first_name.toLowerCase().includes(search.toLowerCase()) ||
      (c.last_name && c.last_name.toLowerCase().includes(search.toLowerCase())) ||
      c.phone.includes(search) ||
      (c.email && c.email.toLowerCase().includes(search.toLowerCase())) ||
      (c.company && c.company.toLowerCase().includes(search.toLowerCase()));

    const matchesStage = selectedStage === "all" || String(c.stage_id) === selectedStage;
    return matchesSearch && matchesStage;
  });

  return (
    <div className="space-y-8 p-6 md:p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Lead CRM & Contacts</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Track voice campaign prospects, qualify inbound leads, and sync appointment outcomes.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            className="gap-2"
            onClick={() => {
              setEditingContact({
                first_name: "",
                last_name: "",
                phone: "",
                email: "",
                company: "",
                stage_id: stages[0]?.id || 1,
                notes: "",
              });
              setModalOpen(true);
            }}
          >
            <UserPlus className="h-4 w-4" /> Add Lead
          </Button>
          <Button variant="outline" size="sm" onClick={fetchData} disabled={loading} className="gap-2">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search leads by name, phone, company..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 h-9 text-xs"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <span className="text-xs text-muted-foreground">Pipeline Stage:</span>
          <Select value={selectedStage} onValueChange={setSelectedStage}>
            <SelectTrigger className="h-9 text-xs w-44">
              <SelectValue placeholder="All Stages" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Stages ({contacts.length})</SelectItem>
              {stages.map((st) => (
                <SelectItem key={st.id} value={String(st.id)}>
                  {st.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <Card className="border-border/60">
        <CardContent className="p-0">
          <div className="rounded-lg overflow-hidden">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow>
                  <TableHead className="text-xs">Contact Name</TableHead>
                  <TableHead className="text-xs">Phone Number</TableHead>
                  <TableHead className="text-xs">Email</TableHead>
                  <TableHead className="text-xs">Company</TableHead>
                  <TableHead className="text-xs">Stage</TableHead>
                  <TableHead className="text-xs">Notes</TableHead>
                  <TableHead className="text-xs text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredContacts.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-12 text-sm text-muted-foreground">
                      No contacts found matching your criteria. Click &quot;Add Lead&quot; to create one.
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredContacts.map((c) => {
                    const stage = stages.find((s) => s.id === c.stage_id);
                    return (
                      <TableRow key={c.id} className="hover:bg-muted/20">
                        <TableCell className="font-semibold text-xs">
                          {c.first_name} {c.last_name || ""}
                        </TableCell>
                        <TableCell className="text-xs font-mono">
                          <span className="flex items-center gap-1.5">
                            <Phone className="h-3 w-3 text-muted-foreground" />
                            {c.phone}
                          </span>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {c.email ? (
                            <span className="flex items-center gap-1.5">
                              <Mail className="h-3 w-3 text-muted-foreground" />
                              {c.email}
                            </span>
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell className="text-xs">
                          {c.company ? (
                            <span className="flex items-center gap-1.5">
                              <Building className="h-3 w-3 text-muted-foreground" />
                              {c.company}
                            </span>
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-[10px] uppercase font-semibold">
                            {stage?.name || "New Lead"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-xs truncate">
                          {c.notes || "—"}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7"
                              onClick={() => {
                                setEditingContact(c);
                                setModalOpen(true);
                              }}
                            >
                              <Edit className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-destructive hover:text-destructive"
                              onClick={() => handleDeleteContact(c.id)}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* CREATE / EDIT CONTACT MODAL */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingContact?.id ? "Edit Contact" : "Add New Lead"}</DialogTitle>
            <DialogDescription>
              Enter lead details for voice campaign outreach and call disposition logging.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">First Name *</Label>
                <Input
                  value={editingContact?.first_name || ""}
                  onChange={(e) => setEditingContact((prev) => prev ? { ...prev, first_name: e.target.value } : null)}
                  placeholder="Rahul"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Last Name</Label>
                <Input
                  value={editingContact?.last_name || ""}
                  onChange={(e) => setEditingContact((prev) => prev ? { ...prev, last_name: e.target.value } : null)}
                  placeholder="Sharma"
                />
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Phone Number *</Label>
              <Input
                value={editingContact?.phone || ""}
                onChange={(e) => setEditingContact((prev) => prev ? { ...prev, phone: e.target.value } : null)}
                placeholder="+91 98765 43210"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Email Address</Label>
              <Input
                value={editingContact?.email || ""}
                onChange={(e) => setEditingContact((prev) => prev ? { ...prev, email: e.target.value } : null)}
                placeholder="rahul@company.com"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Company / Organization</Label>
              <Input
                value={editingContact?.company || ""}
                onChange={(e) => setEditingContact((prev) => prev ? { ...prev, company: e.target.value } : null)}
                placeholder="Innovate Tech"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Pipeline Stage</Label>
              <Select
                value={String(editingContact?.stage_id || stages[0]?.id || 1)}
                onValueChange={(val) => setEditingContact((prev) => prev ? { ...prev, stage_id: parseInt(val) } : null)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {stages.map((st) => (
                    <SelectItem key={st.id} value={String(st.id)}>
                      {st.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Notes / Call Summary</Label>
              <Textarea
                rows={3}
                value={editingContact?.notes || ""}
                onChange={(e) => setEditingContact((prev) => prev ? { ...prev, notes: e.target.value } : null)}
                placeholder="Lead interested in enterprise outbound voice agent..."
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={handleSaveContact} disabled={saving}>
              Save Lead
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
