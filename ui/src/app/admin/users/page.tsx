"use client";

import {
  Award,
  CheckCircle2,
  Clock,
  Coins,
  Edit,
  Loader2,
  Lock,
  Plus,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  UserCheck,
  UserMinus,
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { adminApi, AdminUserItem } from "@/lib/kodewavesApi";

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  // Grant Minutes Modal
  const [grantModalOpen, setGrantModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<AdminUserItem | null>(null);
  const [grantMinutes, setGrantMinutes] = useState(60);
  const [grantNote, setGrantNote] = useState("Admin promotional credit");
  const [granting, setGranting] = useState(false);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const data = await adminApi.getUsers();
      setUsers(data);
    } catch (err) {
      console.error("Failed to load users:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleGrant = async () => {
    if (!selectedUser) return;
    setGranting(true);
    try {
      await adminApi.grantCredits(selectedUser.id, grantMinutes, grantNote);
      setGrantModalOpen(false);
      setSelectedUser(null);
      await fetchUsers();
    } catch (err: any) {
      alert(err.message || "Failed to grant minutes");
    } finally {
      setGranting(false);
    }
  };

  const handleToggleStatus = async (user: AdminUserItem) => {
    const nextStatus = !user.is_active;
    if (!confirm(`Are you sure you want to ${nextStatus ? "activate" : "suspend"} ${user.email}?`)) return;
    try {
      await adminApi.updateUserStatus(user.id, nextStatus);
      await fetchUsers();
    } catch (err: any) {
      alert(err.message || "Failed to update user status");
    }
  };

  const filteredUsers = users.filter(
    (u) =>
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      (u.name && u.name.toLowerCase().includes(search.toLowerCase())) ||
      (u.organization?.name && u.organization.name.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">User Management & Minute Wallets</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Review registered tenant organizations, inspect live wallet minute balances, and award promotional voice credits.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative w-64">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by email, name, or org..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 h-9 text-xs"
            />
          </div>
          <Button variant="outline" size="sm" onClick={fetchUsers} disabled={loading} className="gap-2">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      <Card className="border-border/60">
        <CardHeader>
          <CardTitle className="text-base flex items-center justify-between">
            <span>Registered Accounts ({filteredUsers.length})</span>
            <Badge variant="secondary" className="text-xs">
              Zero KYC Sovereign Tenants
            </Badge>
          </CardTitle>
          <CardDescription>
            All user runs draw against their local organization minute wallet. Admin-granted minutes are available instantly.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-border/60 overflow-hidden">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow>
                  <TableHead className="text-xs">User / Email</TableHead>
                  <TableHead className="text-xs">Organization</TableHead>
                  <TableHead className="text-xs">Role</TableHead>
                  <TableHead className="text-xs">SaaS Plan</TableHead>
                  <TableHead className="text-xs text-right">Wallet Balance</TableHead>
                  <TableHead className="text-xs text-center">Status</TableHead>
                  <TableHead className="text-xs text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredUsers.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8 text-sm text-muted-foreground">
                      No accounts found.
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredUsers.map((u) => (
                    <TableRow key={u.id} className="hover:bg-muted/20">
                      <TableCell>
                        <div className="font-semibold text-xs">{u.email}</div>
                        {u.name && <div className="text-[11px] text-muted-foreground">{u.name}</div>}
                      </TableCell>
                      <TableCell className="text-xs font-medium">
                        {u.organization?.name || `Org #${u.organization?.id || "-"}`}
                      </TableCell>
                      <TableCell>
                        {u.is_superuser ? (
                          <Badge className="bg-purple-500/10 text-purple-600 border-purple-500/20 text-[10px] gap-1">
                            <Shield className="h-3 w-3" /> Superadmin
                          </Badge>
                        ) : (
                          <span className="text-xs text-muted-foreground">Tenant Member</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-[10px] uppercase font-semibold">
                          {u.organization?.current_plan || "Starter"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <span className="font-mono text-xs font-bold text-emerald-600 dark:text-emerald-400">
                          {u.organization?.wallet_balance_minutes?.toFixed(1) ?? "0.0"} mins
                        </span>
                      </TableCell>
                      <TableCell className="text-center">
                        {u.is_active ? (
                          <Badge className="bg-emerald-500/10 text-emerald-600 text-[10px]">
                            Active
                          </Badge>
                        ) : (
                          <Badge variant="destructive" className="text-[10px]">
                            Suspended
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="secondary"
                            size="sm"
                            className="h-7 text-xs gap-1"
                            onClick={() => {
                              setSelectedUser(u);
                              setGrantMinutes(60);
                              setGrantNote("Admin promotional credit");
                              setGrantModalOpen(true);
                            }}
                          >
                            <Coins className="h-3.5 w-3.5 text-amber-500" />
                            Grant Mins
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className={`h-7 w-7 ${u.is_active ? "text-destructive hover:text-destructive" : "text-emerald-500"}`}
                            onClick={() => handleToggleStatus(u)}
                            title={u.is_active ? "Suspend User" : "Activate User"}
                          >
                            {u.is_active ? <UserMinus className="h-3.5 w-3.5" /> : <UserCheck className="h-3.5 w-3.5" />}
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

      {/* GRANT MINUTES DIALOG */}
      <Dialog open={grantModalOpen} onOpenChange={setGrantModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Coins className="h-5 w-5 text-amber-500" />
              Grant Sovereign Minutes
            </DialogTitle>
            <DialogDescription>
              Award free promotional or courtesy voice minutes to {selectedUser?.email}.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label className="text-xs">Minutes to Grant</Label>
              <Input
                type="number"
                min="1"
                value={grantMinutes}
                onChange={(e) => setGrantMinutes(parseInt(e.target.value) || 0)}
              />
              <div className="flex gap-2 mt-1.5">
                {[30, 60, 120, 300, 600].map((preset) => (
                  <Button
                    key={preset}
                    variant="outline"
                    size="sm"
                    className="h-6 text-[10px] px-2"
                    onClick={() => setGrantMinutes(preset)}
                  >
                    +{preset}m
                  </Button>
                ))}
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Internal Audit / Ledger Note</Label>
              <Input
                value={grantNote}
                onChange={(e) => setGrantNote(e.target.value)}
                placeholder="e.g. Free starter grant, customer support issue compensation"
              />
            </div>

            <div className="p-3 bg-muted/40 rounded-lg text-xs space-y-1">
              <div className="flex justify-between text-muted-foreground">
                <span>Current Balance:</span>
                <span className="font-mono">{selectedUser?.organization?.wallet_balance_minutes?.toFixed(1) ?? "0.0"} mins</span>
              </div>
              <div className="flex justify-between font-semibold">
                <span>New Balance After Grant:</span>
                <span className="font-mono text-emerald-500">
                  {((selectedUser?.organization?.wallet_balance_minutes ?? 0) + grantMinutes).toFixed(1)} mins
                </span>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setGrantModalOpen(false)} disabled={granting}>
              Cancel
            </Button>
            <Button onClick={handleGrant} disabled={granting || grantMinutes <= 0}>
              {granting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Grant {grantMinutes} Minutes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
