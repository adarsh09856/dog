"use client";

import {
  Calendar as CalendarIcon,
  CheckCircle2,
  Clock,
  Edit,
  ExternalLink,
  Mail,
  Phone,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  User,
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
import { Appointment, appointmentsApi } from "@/lib/kodewavesApi";

export default function AppointmentsPage() {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingAppt, setEditingAppt] = useState<Partial<Appointment> | null>(null);
  const [saving, setSaving] = useState(false);

  const fetchAppointments = async () => {
    setLoading(true);
    try {
      const data = await appointmentsApi.getAppointments();
      setAppointments(data);
    } catch (err) {
      console.error("Failed to load appointments:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAppointments();
  }, []);

  const handleSaveAppointment = async () => {
    if (!editingAppt || !editingAppt.customer_name || !editingAppt.customer_phone || !editingAppt.start_time) {
      alert("Customer name, phone, and booking start time are required.");
      return;
    }
    setSaving(true);
    try {
      if (editingAppt.id) {
        await appointmentsApi.updateAppointment(editingAppt.id, editingAppt);
      } else {
        await appointmentsApi.createAppointment(editingAppt);
      }
      setModalOpen(false);
      setEditingAppt(null);
      await fetchAppointments();
    } catch (err: any) {
      alert(err.message || "Failed to save appointment");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteAppointment = async (id: string | number) => {
    if (!confirm("Are you sure you want to cancel this booking?")) return;
    try {
      await appointmentsApi.deleteAppointment(id);
      await fetchAppointments();
    } catch (err: any) {
      alert(err.message || "Failed to delete appointment");
    }
  };

  return (
    <div className="space-y-8 p-6 md:p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Calendar Bookings & Appointments</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Voice agents automatically schedule customer callbacks, demos, and site visits into this calendar.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            className="gap-2"
            onClick={() => {
              const now = new Date();
              const end = new Date(now.getTime() + 30 * 60000);
              setEditingAppt({
                title: "Voice Demo Call",
                customer_name: "",
                customer_phone: "",
                customer_email: "",
                start_time: now.toISOString().slice(0, 16),
                end_time: end.toISOString().slice(0, 16),
                status: "confirmed",
                notes: "",
              });
              setModalOpen(true);
            }}
          >
            <Plus className="h-4 w-4" /> Book Appointment
          </Button>
          <Button variant="outline" size="sm" onClick={fetchAppointments} disabled={loading} className="gap-2">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      <Card className="border-border/60">
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <CalendarIcon className="h-5 w-5 text-primary" />
              Scheduled Bookings ({appointments.length})
            </CardTitle>
            <CardDescription>
              Appointments automatically sync with Google Calendar when credentials are connected.
            </CardDescription>
          </div>
          <Badge variant="outline" className="text-xs bg-emerald-500/10 text-emerald-600 border-emerald-500/20 gap-1.5">
            <CheckCircle2 className="h-3 w-3" /> Voice AI Scheduling Active
          </Badge>
        </CardHeader>
        <CardContent className="p-0">
          <div className="rounded-lg overflow-hidden">
            <Table>
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
                {appointments.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-12 text-sm text-muted-foreground">
                      No appointments booked yet. Voice agents will book slots during live conversations.
                    </TableCell>
                  </TableRow>
                ) : (
                  appointments.map((a) => (
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
                        {new Date(a.start_time).toLocaleString([], {
                          dateStyle: "short",
                          timeStyle: "short",
                        })}
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge
                          className={`text-[10px] font-semibold uppercase ${
                            a.status === "confirmed"
                              ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20"
                              : a.status === "pending"
                              ? "bg-amber-500/10 text-amber-600 border-amber-500/20"
                              : "bg-destructive/10 text-destructive border-destructive/20"
                          }`}
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
                            className="h-7 w-7"
                            onClick={() => {
                              setEditingAppt(a);
                              setModalOpen(true);
                            }}
                          >
                            <Edit className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            onClick={() => handleDeleteAppointment(a.id)}
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
                <Label className="text-xs">Start Time *</Label>
                <Input
                  type="datetime-local"
                  value={editingAppt?.start_time ? editingAppt.start_time.slice(0, 16) : ""}
                  onChange={(e) => setEditingAppt((prev) => prev ? { ...prev, start_time: e.target.value } : null)}
                />
              </div>

              <div className="space-y-1">
                <Label className="text-xs">End Time</Label>
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
                onValueChange={(val: any) => setEditingAppt((prev) => prev ? { ...prev, status: val } : null)}
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
            <Button onClick={handleSaveAppointment} disabled={saving}>
              Save Booking
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
