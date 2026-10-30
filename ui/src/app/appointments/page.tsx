"use client";
import {
  Calendar as CalendarIcon,
  CheckCircle2,
  Clock,
  Edit,
  Mail,
  Phone,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import React, { useCallback, useEffect, useMemo, useState } from "react";

import { SavedContactSelector } from "@/components/SavedContactSelector";
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
import { useOrgConfig } from "@/context/OrgConfigContext";
import { appointmentInputTime, appointmentTimes } from "@/lib/appointmentTime";
import { useAuth } from "@/lib/auth";
import { Appointment, appointmentsApi } from "@/lib/kodewavesApi";

export default function AppointmentsPage() {
  const { user, loading: authLoading } = useAuth();
  const { organizationPreferences, loading: configLoading } = useOrgConfig();
  const timeZone = organizationPreferences?.timezone || "Asia/Kolkata";
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingAppt, setEditingAppt] = useState<Partial<Appointment> | null>(null);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const fetchAppointments = useCallback(async () => {
    if (authLoading || !user) return;
    setLoadError(null);
    setLoading(true);
    try {
      const data = await appointmentsApi.getAppointments();
      setAppointments(data);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Unable to load this page. Please retry.");
      console.error("Failed to load appointments:", err);
    } finally {
      setLoading(false);
    }
  }, [authLoading, user]);

  useEffect(() => {
    if (authLoading || !user) return;
    void fetchAppointments();
  }, [authLoading, user, fetchAppointments]);

  const filteredAppointments = useMemo(() => {
    const query = search.trim().toLowerCase();
    return appointments.filter((appointment) => {
      const matchesStatus = statusFilter === "all" || appointment.status === statusFilter;
      const matchesSearch = !query || [appointment.title, appointment.customer_name, appointment.customer_phone, appointment.customer_email]
        .some((value) => value?.toLowerCase().includes(query));
      return matchesStatus && matchesSearch;
    });
  }, [appointments, search, statusFilter]);

  const openNewAppointment = () => {
    const now = new Date();
    const end = new Date(now.getTime() + 30 * 60000);
    setEditingAppt({
      title: "Voice Demo Call", customer_name: "", customer_phone: "", customer_email: "",
      start_time: appointmentInputTime(now, timeZone), end_time: appointmentInputTime(end, timeZone),
      status: "confirmed", notes: "",
    });
    setModalOpen(true);
  };

  const openEditAppointment = (appointment: Appointment) => {
    setEditingAppt({ ...appointment, start_time: appointmentInputTime(appointment.start_time, timeZone), end_time: appointmentInputTime(appointment.end_time, timeZone) });
    setModalOpen(true);
  };

  const formatAppointmentDate = (value: string) => new Date(value).toLocaleString([], {
    timeZone, weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });

  const statusClass = (status: string) => status === "confirmed"
    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
    : status === "pending"
      ? "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300"
      : status === "completed"
        ? "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300"
        : "border-border bg-muted text-muted-foreground";

  const handleSaveAppointment = async () => {
    if (!editingAppt || !editingAppt.customer_name || !editingAppt.customer_phone || !editingAppt.start_time) {
      alert("Customer name, phone, and booking start time are required.");
      return;
    }
    setSaving(true);
    try {
      const payload = { ...editingAppt, ...appointmentTimes(editingAppt.start_time, editingAppt.end_time, timeZone) };
      if (editingAppt.id) {
        await appointmentsApi.updateAppointment(editingAppt.id, payload);
      } else {
        await appointmentsApi.createAppointment(payload);
      }
      setModalOpen(false);
      setEditingAppt(null);
      await fetchAppointments();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to save appointment");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteAppointment = async (id: string | number) => {
    if (!confirm("Are you sure you want to cancel this booking?")) return;
    try {
      await appointmentsApi.deleteAppointment(id);
      await fetchAppointments();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete appointment");
    }
  };

  return (
    <main className="mx-auto w-full max-w-screen-2xl space-y-7 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      {loadError && <div role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"><div className="flex flex-wrap items-center justify-between gap-3"><span>{loadError}</span><Button variant="outline" size="sm" onClick={fetchAppointments}>Try again</Button></div></div>}
      {/* Header */}
      <header className="relative isolate overflow-hidden rounded-3xl border border-border bg-gradient-to-br from-card via-card to-primary/10 px-5 py-6 sm:px-8 sm:py-8">
        <div aria-hidden="true" className="absolute -right-12 -top-20 -z-10 h-64 w-64 rounded-full bg-primary/10 blur-3xl" />
        <div>
          <span className="mb-3 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-xs font-semibold uppercase tracking-[.16em] text-primary"><CalendarIcon className="h-3.5 w-3.5" /> Scheduling</span>
          <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">Appointments</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
            Keep callbacks, demos, and site visits organized across your team.
          </p>
        </div>
        <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:items-center">
          <Button
            size="default"
            disabled={configLoading}
            className="h-11 gap-2 sm:w-auto"
            onClick={openNewAppointment}
          >
            <Plus className="h-4 w-4" /> Book appointment
          </Button>
          <Button variant="outline" size="default" onClick={fetchAppointments} disabled={loading} className="h-11 gap-2 sm:w-auto">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </header>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Appointment overview">
        {[
          { label: "All bookings", value: appointments.length, note: "Appointments in workspace", icon: CalendarIcon, tone: "text-primary bg-primary/10" },
          { label: "Upcoming", value: appointments.filter((appointment) => new Date(appointment.start_time).getTime() >= Date.now() && appointment.status !== "cancelled").length, note: "Scheduled from now", icon: Clock, tone: "text-sky-600 bg-sky-500/10" },
          { label: "Confirmed", value: appointments.filter((appointment) => appointment.status === "confirmed").length, note: "Ready for the next step", icon: CheckCircle2, tone: "text-emerald-600 bg-emerald-500/10" },
          { label: "Needs follow-up", value: appointments.filter((appointment) => appointment.status === "pending").length, note: "Awaiting confirmation", icon: Phone, tone: "text-amber-600 bg-amber-500/10" },
        ].map((metric) => <Card key={metric.label} className="rounded-2xl border-border/70 shadow-sm"><CardContent className="p-4 sm:p-5"><div className="flex items-start justify-between gap-2"><span className="text-xs font-medium text-muted-foreground sm:text-sm">{metric.label}</span><span className={`rounded-xl p-2 ${metric.tone}`}><metric.icon className="h-4 w-4" /></span></div><p className="mt-3 text-2xl font-semibold tabular-nums tracking-tight sm:text-3xl">{metric.value.toLocaleString()}</p><p className="mt-1 text-[11px] text-muted-foreground sm:text-xs">{metric.note}</p></CardContent></Card>)}
      </section>

      <Card className="overflow-hidden rounded-2xl border-border/70 shadow-sm">
        <CardHeader className="gap-4 border-b border-border/70 bg-muted/20 px-4 py-5 sm:px-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><CardTitle className="text-lg">Scheduled bookings <span className="ml-1 text-sm font-normal text-muted-foreground">{filteredAppointments.length} of {appointments.length}</span></CardTitle><CardDescription className="mt-1">Find a booking, check its status, or update the details.</CardDescription></div>
            <Badge variant="outline" className="gap-1.5 border-emerald-500/20 bg-emerald-500/10 text-xs text-emerald-700 dark:text-emerald-300"><CheckCircle2 className="h-3 w-3" /> Workspace bookings</Badge>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <label className="relative block flex-1"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><Input aria-label="Search appointments" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by customer, phone, or meeting" className="pl-9" /></label>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger aria-label="Filter appointments by status" className="sm:w-48"><SelectValue placeholder="All statuses" /></SelectTrigger>
              <SelectContent><SelectItem value="all">All statuses</SelectItem><SelectItem value="confirmed">Confirmed</SelectItem><SelectItem value="pending">Pending</SelectItem><SelectItem value="completed">Completed</SelectItem><SelectItem value="cancelled">Cancelled</SelectItem></SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? <div className="grid gap-3 p-4 sm:grid-cols-2 sm:p-6">{[1, 2, 3, 4].map((item) => <div key={item} className="h-32 animate-pulse rounded-xl bg-muted" />)}</div> : appointments.length === 0 ? <div className="px-5 py-14 text-center"><span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-primary/10 text-primary"><CalendarIcon className="h-5 w-5" /></span><h2 className="mt-4 font-semibold">No appointments yet</h2><p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">Book a customer callback or demo, or connect the Book Appointment tool to your voice agent.</p><Button disabled={configLoading} onClick={openNewAppointment} className="mt-5 gap-2"><Plus className="h-4 w-4" /> Book an appointment</Button></div> : filteredAppointments.length === 0 ? <div className="px-5 py-12 text-center"><p className="font-medium">No appointments match these filters</p><Button variant="link" onClick={() => { setSearch(""); setStatusFilter("all"); }}>Clear filters</Button></div> : <>
          <div className="grid gap-3 p-4 sm:grid-cols-2 sm:p-6 lg:hidden">
            {filteredAppointments.map((appointment) => <article key={appointment.id} className="min-w-0 rounded-2xl border border-border bg-card p-4 shadow-sm">
              <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate font-semibold">{appointment.title || "Appointment"}</p><p className="mt-1 truncate text-sm text-muted-foreground">{appointment.customer_name || "Unnamed customer"}</p></div><Badge variant="outline" className={`shrink-0 capitalize ${statusClass(appointment.status)}`}>{appointment.status}</Badge></div>
              <div className="mt-4 flex items-start gap-2 rounded-xl bg-muted/50 p-3"><Clock className="mt-0.5 h-4 w-4 shrink-0 text-primary" /><div><p className="text-sm font-medium">{formatAppointmentDate(appointment.start_time)}</p><p className="mt-0.5 text-xs text-muted-foreground">{timeZone}</p></div></div>
              <div className="mt-3 space-y-1 text-sm text-muted-foreground"><p className="flex items-center gap-2"><Phone className="h-3.5 w-3.5" />{appointment.customer_phone || "No phone"}</p>{appointment.customer_email && <p className="flex items-center gap-2 truncate"><Mail className="h-3.5 w-3.5 shrink-0" />{appointment.customer_email}</p>}</div>
              {appointment.notes && <p className="mt-3 line-clamp-2 border-t border-border pt-3 text-xs text-muted-foreground">{appointment.notes}</p>}
              <div className="mt-4 flex gap-2 border-t border-border pt-3"><Button variant="outline" size="sm" disabled={configLoading} className="flex-1 gap-2" onClick={() => openEditAppointment(appointment)}><Edit className="h-3.5 w-3.5" /> Edit</Button><Button variant="ghost" size="sm" className="gap-2 text-destructive hover:text-destructive" onClick={() => handleDeleteAppointment(appointment.id)}><Trash2 className="h-3.5 w-3.5" /> Cancel booking</Button></div>
            </article>)}
          </div>
          <div className="hidden overflow-x-auto lg:block">
            <Table className="min-w-[900px]">
              <TableHeader className="bg-muted/40">
                <TableRow>
                  <TableHead className="text-xs">Meeting Title</TableHead>
                  <TableHead className="text-xs">Customer</TableHead>
                  <TableHead className="text-xs">Phone / Email</TableHead>
                  <TableHead className="text-xs">Time & Duration</TableHead>
                  <TableHead className="text-xs text-center">Status</TableHead>
                  <TableHead className="text-xs">Notes</TableHead>
                  <TableHead className="text-xs text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredAppointments.map((a) => (
                    <TableRow key={a.id} className="hover:bg-muted/20">
                      <TableCell className="font-semibold text-xs">{a.title}</TableCell>
                      <TableCell className="text-xs font-medium">{a.customer_name}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        <div className="flex items-center gap-1 font-mono">
                          <Phone className="h-3 w-3" /> {a.customer_phone}
                        </div>
                        {a.customer_email && (
                          <div className="flex items-center gap-1 text-[11px]">
                            <Mail className="h-3 w-3" /> {a.customer_email}
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="text-xs font-mono text-primary font-medium">
                        {formatAppointmentDate(a.start_time)}
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge
                          variant="outline"
                          className={`text-[10px] font-semibold uppercase ${statusClass(a.status)}`}
                        >
                          {a.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-xs truncate">
                        {a.notes || "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            disabled={configLoading}
                            className="h-7 w-7"
                            aria-label={`Edit ${a.title || "appointment"} for ${a.customer_name || "customer"}`}
                            onClick={() => openEditAppointment(a)}
                          >
                            <Edit className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            aria-label={`Cancel ${a.title || "appointment"} for ${a.customer_name || "customer"}`}
                            onClick={() => handleDeleteAppointment(a.id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </div>
          </>}
        </CardContent>
      </Card>

      {/* CREATE / EDIT APPOINTMENT MODAL */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingAppt?.id ? "Edit Appointment" : "Schedule New Appointment"}</DialogTitle>
            <DialogDescription>
              Book customer callback or demo session.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            {!editingAppt?.id && <SavedContactSelector
              value={editingAppt?.contact_id}
              onSelect={(contact) => setEditingAppt(previous => previous ? {
                ...previous,
                contact_id: contact?.id ?? null,
                ...(contact ? {
                  customer_name: [contact.first_name, contact.last_name].filter(Boolean).join(" "),
                  customer_phone: contact.phone,
                  customer_email: contact.email ?? "",
                } : {}),
              } : null)}
            />}
            <div className="space-y-1">
              <Label className="text-xs">Meeting Title</Label>
              <Input
                value={editingAppt?.title || ""}
                onChange={(e) => setEditingAppt((prev) => prev ? { ...prev, title: e.target.value } : null)}
                placeholder="Product Demo Consultation"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Customer Name *</Label>
              <Input
                value={editingAppt?.customer_name || ""}
                onChange={(e) => setEditingAppt((prev) => prev ? { ...prev, customer_name: e.target.value } : null)}
                placeholder="Priya Verma"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Customer Phone *</Label>
                <Input
                  value={editingAppt?.customer_phone || ""}
                  onChange={(e) => setEditingAppt((prev) => prev ? { ...prev, customer_phone: e.target.value } : null)}
                  placeholder="+91 99887 76655"
                />
              </div>

              <div className="space-y-1">
                <Label className="text-xs">Customer Email</Label>
                <Input
                  value={editingAppt?.customer_email || ""}
                  onChange={(e) => setEditingAppt((prev) => prev ? { ...prev, customer_email: e.target.value } : null)}
                  placeholder="priya@domain.com"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Start Time * ({timeZone})</Label>
                <Input
                  type="datetime-local"
                  value={editingAppt?.start_time ? editingAppt.start_time.slice(0, 16) : ""}
                  onChange={(e) => setEditingAppt((prev) => prev ? { ...prev, start_time: e.target.value } : null)}
                />
              </div>

              <div className="space-y-1">
                <Label className="text-xs">End Time ({timeZone})</Label>
                <Input
                  type="datetime-local"
                  value={editingAppt?.end_time ? editingAppt.end_time.slice(0, 16) : ""}
                  onChange={(e) => setEditingAppt((prev) => prev ? { ...prev, end_time: e.target.value } : null)}
                />
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Status</Label>
              <Select
                value={editingAppt?.status || "confirmed"}
                onValueChange={(val) => setEditingAppt((prev) => prev ? { ...prev, status: val } : null)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="confirmed">Confirmed</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="cancelled">Cancelled</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={handleSaveAppointment} disabled={saving || configLoading}>
              Save Booking
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
