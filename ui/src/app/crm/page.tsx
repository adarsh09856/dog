"use client";

import {
  ArrowDownRight,
  Building,
  CheckCircle2,
  Edit,
  Mail,
  Phone,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { useAuth } from "@/lib/auth";
import { Contact, crmApi, LeadStage } from "@/lib/kodewavesApi";

import styles from "./CRMWorkspace.module.css";

const contactName = (contact: Contact) =>
  [contact.first_name, contact.last_name].filter(Boolean).join(" ").trim() || "Unnamed contact";

const initials = (contact: Contact) => {
  const name = contactName(contact);
  return name === "Unnamed contact"
    ? "?"
    : name.split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
};

export default function CRMPage() {
  const { user, loading: authLoading } = useAuth();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [stages, setStages] = useState<LeadStage[]>([]);
  const [search, setSearch] = useState("");
  const [selectedStage, setSelectedStage] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingContact, setEditingContact] = useState<Partial<Contact> | null>(null);
  const [saving, setSaving] = useState(false);

  const fetchData = async () => {
    if (authLoading || !user) return;
    setLoadError(null);
    setLoading(true);
    try {
      const [fetchedContacts, fetchedStages] = await Promise.all([
        crmApi.getContacts(),
        crmApi.getStages(),
      ]);
      setContacts(fetchedContacts);
      setStages(fetchedStages || []);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Unable to load CRM records. Please retry.");
      console.error("Failed to load CRM data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (authLoading || !user) return;
    void fetchData();
    // CRM API is stable for the lifetime of the authenticated page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user]);

  const openNewContact = () => {
    setEditingContact({
      first_name: "",
      last_name: "",
      phone: "",
      email: "",
      company: "",
      stage_id: stages[0]?.id,
      notes: "",
    });
    setModalOpen(true);
  };

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
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to save contact");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteContact = async (id: string | number) => {
    if (!confirm("Are you sure you want to delete this contact?")) return;
    try {
      await crmApi.deleteContact(id);
      await fetchData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete contact");
    }
  };

  const stageCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const contact of contacts) {
      if (contact.stage_id) {
        const id = String(contact.stage_id);
        counts.set(id, (counts.get(id) || 0) + 1);
      }
    }
    return counts;
  }, [contacts]);

  const filteredContacts = useMemo(() => {
    const query = search.trim().toLowerCase();
    return contacts.filter((contact) => {
      const matchesSearch = !query || [
        contact.first_name,
        contact.last_name,
        contact.phone,
        contact.email,
        contact.company,
      ].some((value) => value?.toLowerCase().includes(query));
      const matchesStage = selectedStage === "all" || String(contact.stage_id) === selectedStage;
      return matchesSearch && matchesStage;
    });
  }, [contacts, search, selectedStage]);

  const emailCount = contacts.filter((contact) => Boolean(contact.email)).length;
  const activeStageName = stages.find((stage) => String(stage.id) === selectedStage)?.name;

  return (
    <main className={styles.page}>
      <section className={styles.hero} aria-labelledby="crm-title">
        <div className={styles.heroCopy}>
          <div className={styles.eyebrow}><span /> RELATIONSHIPS / CRM</div>
          <h1 id="crm-title">Know every lead.<br /><em>Move the right ones forward.</em></h1>
          <p>Keep contact details, qualification stage and call context together, so your team always knows what to do next.</p>
          <div className={styles.heroActions}>
            <Button onClick={openNewContact} className={styles.primaryAction}>
              <UserPlus aria-hidden="true" /> Add a lead
            </Button>
            <Button variant="outline" onClick={() => void fetchData()} disabled={loading} className={styles.secondaryAction}>
              <RefreshCw aria-hidden="true" className={loading ? "animate-spin" : ""} /> Refresh records
            </Button>
          </div>
        </div>
        <aside className={styles.heroAside} aria-label="Contact snapshot">
          <div className={styles.snapshotTop}><Users aria-hidden="true" /><span>YOUR CONTACT BOOK</span></div>
          <strong>{loading ? "—" : contacts.length.toLocaleString()}</strong>
          <span className={styles.snapshotLabel}>people and organizations</span>
          <div className={styles.snapshotFoot}><span><Mail aria-hidden="true" /> {emailCount} with email</span><ArrowDownRight aria-hidden="true" /></div>
        </aside>
        <div className={styles.heroOrb} aria-hidden="true" />
      </section>

      <section className={styles.metrics} aria-label="Contact insights">
        <article className={styles.metric}>
          <span className={styles.metricIcon}><Users aria-hidden="true" /></span>
          <div><span className={styles.metricLabel}>TOTAL CONTACTS</span><strong>{loading ? "—" : contacts.length.toLocaleString()}</strong><p>Across every qualification stage</p></div>
        </article>
        <article className={styles.metric}>
          <span className={styles.metricIcon}><CheckCircle2 aria-hidden="true" /></span>
          <div><span className={styles.metricLabel}>PIPELINE STAGES</span><strong>{loading ? "—" : stages.length}</strong><p>Steps your team uses to qualify leads</p></div>
        </article>
        <article className={styles.metric}>
          <span className={styles.metricIcon}><Mail aria-hidden="true" /></span>
          <div><span className={styles.metricLabel}>EMAIL COVERAGE</span><strong>{loading ? "—" : `${contacts.length ? Math.round((emailCount / contacts.length) * 100) : 0}%`}</strong><p>{loading ? "Loading contacts" : `${emailCount} of ${contacts.length} contacts have an email`}</p></div>
        </article>
      </section>

      <section className={styles.pipeline} aria-labelledby="pipeline-heading">
        <div className={styles.pipelineHeading}>
          <div><span className={styles.sectionKicker}>QUALIFICATION</span><h2 id="pipeline-heading">Your pipeline</h2></div>
          <span className={styles.pipelineHint}>Choose a stage to focus the contact list</span>
        </div>
        <div className={styles.stageRail} role="group" aria-label="Filter contacts by pipeline stage">
          <button type="button" aria-pressed={selectedStage === "all"} className={selectedStage === "all" ? styles.stageActive : styles.stageButton} onClick={() => setSelectedStage("all")}>
            <span>All contacts</span><strong>{contacts.length}</strong>
          </button>
          {stages.map((stage) => {
            const active = selectedStage === String(stage.id);
            return (
                <button key={stage.id} type="button" aria-pressed={active} className={active ? styles.stageActive : styles.stageButton} onClick={() => setSelectedStage(String(stage.id))}>
                  <span>{stage.name}</span><strong>{stageCounts.get(String(stage.id)) || 0}</strong>
                </button>
            );
          })}
        </div>
      </section>

      <section className={styles.records} aria-labelledby="records-heading">
        <header className={styles.recordsHeader}>
          <div className={styles.recordsTitle}>
            <span className={styles.sectionKicker}>WORKSPACE DIRECTORY</span>
            <h2 id="records-heading">Contacts <span>{loading ? "…" : filteredContacts.length}</span></h2>
            <p>{activeStageName ? `Showing ${activeStageName} leads` : "Every person and organization in your workspace, in one clear list."}</p>
          </div>
          <div className={styles.filters}>
            <label className={styles.searchBox}>
              <Search aria-hidden="true" />
              <span className="sr-only">Search contacts</span>
              <Input placeholder="Search name, phone, email or company" value={search} onChange={(event) => setSearch(event.target.value)} />
              {search && <button type="button" aria-label="Clear search" onClick={() => setSearch("")}>×</button>}
            </label>
            <label className={styles.stageSelect}>
              <span className="sr-only">Pipeline stage</span>
              <Select value={selectedStage} onValueChange={setSelectedStage}>
                <SelectTrigger aria-label="Pipeline stage"><SelectValue placeholder="All stages" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All stages ({contacts.length})</SelectItem>
                  {stages.map((stage) => <SelectItem key={stage.id} value={String(stage.id)}>{stage.name} ({stageCounts.get(String(stage.id)) || 0})</SelectItem>)}
                </SelectContent>
              </Select>
            </label>
          </div>
        </header>

        {loadError ? (
          <div role="alert" className={styles.errorState}>
            <div><strong>Contacts could not be loaded</strong><p>{loadError}</p></div>
            <Button variant="outline" onClick={() => void fetchData()} disabled={loading}>Try again</Button>
          </div>
        ) : loading ? (
          <div role="status" aria-live="polite" className={styles.loadingState}>
            <RefreshCw aria-hidden="true" className="animate-spin" /><span>Loading your contacts…</span>
          </div>
        ) : filteredContacts.length === 0 ? (
          <div className={styles.emptyState}>
            <span className={styles.emptyIcon}><Users aria-hidden="true" /></span>
            <h3>{contacts.length === 0 ? "Start with your first lead" : "No contacts match this view"}</h3>
            <p>{contacts.length === 0 ? "Add a contact to give your team a place to track conversations and qualification." : "Try another search or choose a different pipeline stage."}</p>
            {contacts.length === 0
              ? <Button onClick={openNewContact}><Plus aria-hidden="true" /> Add your first lead</Button>
              : <Button variant="outline" onClick={() => { setSearch(""); setSelectedStage("all"); }}>Clear filters</Button>}
          </div>
        ) : (
          <>
            <div className={styles.desktopTable}>
              <Table className="min-w-[900px]">
                <TableHeader>
                  <TableRow>
                    <TableHead>Contact</TableHead><TableHead>Contact details</TableHead><TableHead>Organization</TableHead><TableHead>Stage</TableHead><TableHead>Call notes</TableHead><TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredContacts.map((contact) => {
                    const stage = stages.find((item) => String(item.id) === String(contact.stage_id));
                    return (
                      <TableRow key={contact.id}>
                        <TableCell>
                          <div className={styles.contactIdentity}><span className={styles.avatar}>{initials(contact)}</span><div><strong>{contactName(contact)}</strong><span>Contact #{contact.id}</span></div></div>
                        </TableCell>
                        <TableCell><div className={styles.contactDetails}><span><Phone aria-hidden="true" />{contact.phone || "No phone"}</span><span><Mail aria-hidden="true" />{contact.email || "No email added"}</span></div></TableCell>
                        <TableCell>{contact.company ? <span className={styles.company}><Building aria-hidden="true" />{contact.company}</span> : <span className={styles.mutedValue}>Not specified</span>}</TableCell>
                        <TableCell><Badge variant="outline" className={styles.stageBadge}>{stage?.name || "New lead"}</Badge></TableCell>
                        <TableCell><span className={styles.notes} title={contact.notes || undefined}>{contact.notes || "No notes yet"}</span></TableCell>
                        <TableCell><div className={styles.rowActions}>
                          <Button variant="ghost" size="sm" aria-label={`Edit ${contactName(contact)}`} onClick={() => { setEditingContact(contact); setModalOpen(true); }}><Edit aria-hidden="true" /> Edit</Button>
                          <Button variant="ghost" size="icon" aria-label={`Delete ${contactName(contact)}`} className={styles.deleteButton} onClick={() => void handleDeleteContact(contact.id)}><Trash2 aria-hidden="true" /></Button>
                        </div></TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
            <div className={styles.mobileCards}>
              {filteredContacts.map((contact) => {
                const stage = stages.find((item) => String(item.id) === String(contact.stage_id));
                return <article className={styles.mobileContact} key={contact.id}>
                  <div className={styles.mobileContactHead}><span className={styles.avatar}>{initials(contact)}</span><div><strong>{contactName(contact)}</strong><span>{contact.company || "Individual contact"}</span></div><Badge variant="outline" className={styles.stageBadge}>{stage?.name || "New lead"}</Badge></div>
                  <div className={styles.mobileContactDetails}><a href={`tel:${contact.phone}`}><Phone aria-hidden="true" />{contact.phone || "No phone"}</a>{contact.email && <a href={`mailto:${contact.email}`}><Mail aria-hidden="true" />{contact.email}</a>}</div>
                  {contact.notes && <p className={styles.mobileNotes}>{contact.notes}</p>}
                  <div className={styles.mobileActions}><Button variant="outline" size="sm" onClick={() => { setEditingContact(contact); setModalOpen(true); }}><Edit aria-hidden="true" /> Edit contact</Button><Button variant="ghost" size="sm" className={styles.deleteButton} onClick={() => void handleDeleteContact(contact.id)}><Trash2 aria-hidden="true" /> Delete</Button></div>
                </article>;
              })}
            </div>
          </>
        )}
      </section>

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingContact?.id ? "Edit contact" : "Add a lead"}</DialogTitle>
            <DialogDescription>Save the details your team needs to follow up and keep the conversation moving.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label htmlFor="crm-first-name" className="text-xs">First name *</Label><Input id="crm-first-name" autoComplete="given-name" value={editingContact?.first_name || ""} onChange={(event) => setEditingContact((prev) => prev ? { ...prev, first_name: event.target.value } : null)} placeholder="Rahul" /></div>
              <div className="space-y-1"><Label htmlFor="crm-last-name" className="text-xs">Last name</Label><Input id="crm-last-name" autoComplete="family-name" value={editingContact?.last_name || ""} onChange={(event) => setEditingContact((prev) => prev ? { ...prev, last_name: event.target.value } : null)} placeholder="Sharma" /></div>
            </div>
            <div className="space-y-1"><Label htmlFor="crm-phone" className="text-xs">Phone number *</Label><Input id="crm-phone" autoComplete="tel" inputMode="tel" value={editingContact?.phone || ""} onChange={(event) => setEditingContact((prev) => prev ? { ...prev, phone: event.target.value } : null)} placeholder="+91 98765 43210" /></div>
            <div className="space-y-1"><Label htmlFor="crm-email" className="text-xs">Email address</Label><Input id="crm-email" autoComplete="email" type="email" value={editingContact?.email || ""} onChange={(event) => setEditingContact((prev) => prev ? { ...prev, email: event.target.value } : null)} placeholder="rahul@company.com" /></div>
            <div className="space-y-1"><Label htmlFor="crm-company" className="text-xs">Company or organization</Label><Input id="crm-company" autoComplete="organization" value={editingContact?.company || ""} onChange={(event) => setEditingContact((prev) => prev ? { ...prev, company: event.target.value } : null)} placeholder="Innovate Tech" /></div>
            <div className="space-y-1"><Label htmlFor="crm-stage" className="text-xs">Pipeline stage</Label><Select value={String(editingContact?.stage_id || stages[0]?.id || 1)} onValueChange={(value) => setEditingContact((prev) => prev ? { ...prev, stage_id: value } : null)}><SelectTrigger id="crm-stage"><SelectValue /></SelectTrigger><SelectContent>{stages.map((stage) => <SelectItem key={stage.id} value={String(stage.id)}>{stage.name}</SelectItem>)}</SelectContent></Select></div>
            <div className="space-y-1"><Label htmlFor="crm-notes" className="text-xs">Notes or call summary</Label><Textarea id="crm-notes" rows={3} value={editingContact?.notes || ""} onChange={(event) => setEditingContact((prev) => prev ? { ...prev, notes: event.target.value } : null)} placeholder="What should the team remember before the next conversation?" /></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setModalOpen(false)} disabled={saving}>Cancel</Button><Button onClick={() => void handleSaveContact()} disabled={saving}>{saving ? "Saving…" : "Save contact"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
