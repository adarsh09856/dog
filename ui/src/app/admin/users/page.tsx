"use client";

import {
  AlertTriangle,
  ArrowUpDown,
  Coins,
  Download,
  Edit,
  ExternalLink,
  KeyRound,
  Loader2,
  Lock,
  MoreHorizontal,
  PhoneCall,
  Plus,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  Sparkles,
  Trash2,
  UserCheck,
  UserMinus,
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { adminApi, AdminUserItem } from "@/lib/kodewavesApi";

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Selected User for Modals
  const [selectedUser, setSelectedUser] = useState<AdminUserItem | null>(null);

  // 1. Create User Modal State
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createForm, setCreateForm] = useState({
    email: "",
    password: "",
    name: "",
    is_superuser: false,
    has_local_ai_access: false,
    plan_code: "starter",
    initial_minutes: 60,
  });

  // 2. Grant Minutes Modal State
  const [grantModalOpen, setGrantModalOpen] = useState(false);
  const [grantMinutes, setGrantMinutes] = useState(60);
  const [grantNote, setGrantNote] = useState("Admin promotional credit");

  // 3. Edit User Modal State
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editForm, setEditForm] = useState({
    is_superuser: false,
    has_local_ai_access: false,
    is_wallet_frozen: false,
    max_concurrent_calls: 2,
    max_agents: 10,
    enable_campaigns: true,
    enable_crm: true,
    enable_widgets: true,
    enable_appointments: true,
    enable_forms: true,
    enable_byok: true,
    plan_name: "Starter",
    wallet_balance_minutes: 0,
  });


  // 4. Reset Password Modal State
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [newPassword, setNewPassword] = useState("");

  // 5. Delete Confirm Modal State
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const data = await adminApi.getUsers({
        search: search || undefined,
        role: roleFilter !== "all" ? roleFilter : undefined,
        status: statusFilter !== "all" ? statusFilter : undefined,
      });
      setUsers(data);
      setError(null);
    } catch (err: any) {
      console.error("Failed to load users:", err);
      setError(err.message || "Failed to load users from database");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const handler = setTimeout(() => {
      fetchUsers();
    }, 300);
    return () => clearTimeout(handler);
  }, [search, roleFilter, statusFilter]);

  // Handlers
  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createForm.email || !createForm.password) {
      alert("Email and password are required.");
      return;
    }
    setActionLoading(true);
    try {
      await adminApi.createUser(createForm);
      setCreateModalOpen(false);
      setCreateForm({
        email: "",
        password: "",
        name: "",
        is_superuser: false,
        has_local_ai_access: false,
        plan_code: "starter",
        initial_minutes: 60,
      });
      await fetchUsers();
    } catch (err: any) {
      alert(err.message || "Failed to create user");
    } finally {
      setActionLoading(false);
    }
  };

  const handleGrantMinutes = async () => {
    if (!selectedUser) return;
    setActionLoading(true);
    try {
      await adminApi.grantCredits(selectedUser.id, grantMinutes, grantNote);
      setGrantModalOpen(false);
      setSelectedUser(null);
      await fetchUsers();
    } catch (err: any) {
      alert(err.message || "Failed to grant minutes");
    } finally {
      setActionLoading(false);
    }
  };

  const handleEditUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser) return;
    setActionLoading(true);
    try {
      await adminApi.updateUser(selectedUser.id, editForm);
      setEditModalOpen(false);
      setSelectedUser(null);
      await fetchUsers();
    } catch (err: any) {
      alert(err.message || "Failed to update user");
    } finally {
      setActionLoading(false);
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser || !newPassword) return;
    setActionLoading(true);
    try {
      await adminApi.resetPassword(selectedUser.id, newPassword);
      setPasswordModalOpen(false);
      setNewPassword("");
      setSelectedUser(null);
      alert(`Password updated successfully for ${selectedUser.email}`);
    } catch (err: any) {
      alert(err.message || "Failed to reset password");
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleStatus = async (user: AdminUserItem) => {
    const nextStatus = !user.is_active;
    const confirmMsg = nextStatus
      ? `Reactivate account for ${user.email}?`
      : `SUSPEND account for ${user.email}? This will revoke access and drop active calls immediately.`;
    if (!confirm(confirmMsg)) return;
    try {
      await adminApi.updateUserStatus(user.id, nextStatus);
      await fetchUsers();
    } catch (err: any) {
      alert(err.message || "Failed to update user status");
    }
  };

  const handleImpersonate = async (user: AdminUserItem) => {
    if (!confirm(`Log in as ${user.email} and switch to their workspace?`)) return;
    try {
      const res = await adminApi.impersonateUser(user.id);
      if (res.token) {
        // Preserve admin session so admin can exit impersonation anytime
        const originalAdminToken = document.cookie
          .split("; ")
          .find((row) => row.startsWith("kodewaves_auth_token=") || row.startsWith("dograh_auth_token="))
          ?.split("=")[1];
        if (originalAdminToken) {
          localStorage.setItem("kodewaves_impersonator_token", originalAdminToken);
          localStorage.setItem("kodewaves_impersonated_email", user.email);
        }
        document.cookie = `kodewaves_auth_token=${res.token}; path=/; max-age=86400`;
        document.cookie = `dograh_auth_token=${res.token}; path=/; max-age=86400`;
        document.cookie = `oss_token=${res.token}; path=/; max-age=86400`;
        window.location.href = res.redirect_url || "/workflow";
      }
    } catch (err: any) {
      alert(err.message || "Failed to impersonate user");
    }
  };

  const handleDeleteUser = async () => {
    if (!selectedUser) return;
    setActionLoading(true);
    try {
      await adminApi.deleteUser(selectedUser.id);
      setDeleteModalOpen(false);
      setSelectedUser(null);
      await fetchUsers();
    } catch (err: any) {
      alert(err.message || "Failed to delete user");
    } finally {
      setActionLoading(false);
    }
  };

  const handleExportCSV = () => {
    if (users.length === 0) {
      alert("No users to export.");
      return;
    }
    const headers = ["ID", "Email", "Name", "Role", "Organization", "Wallet_Minutes", "Status", "Calls_Count", "Created_At"];
    const rows = users.map((u) => [
      u.id,
      `"${u.email || ""}"`,
      `"${u.name || ""}"`,
      u.is_superuser ? "Superadmin" : "User",
      `"${u.organization_name || u.organization?.name || ""}"`,
      u.wallet_balance_minutes ?? u.organization?.wallet_balance_minutes ?? 0,
      u.is_active ? "Active" : "Suspended",
      u.total_calls ?? 0,
      u.created_at || "",
    ]);
    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `kodewaves_users_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">User Management & Platform Governance</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Complete AgentLabs-grade controls: provision users, grant promo credits, adjust quotas, reset passwords, and manage status.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleExportCSV} className="gap-2">
            <Download className="h-3.5 w-3.5" />
            Export CSV
          </Button>
          <Button size="sm" onClick={() => setCreateModalOpen(true)} className="gap-2">
            <UserPlus className="h-3.5 w-3.5" />
            Create User
          </Button>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="flex items-center justify-between p-4 rounded-lg bg-destructive/10 border border-destructive/30 text-destructive text-sm">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>Database Error: {error}</span>
          </div>
          <Button variant="outline" size="sm" onClick={fetchUsers} className="text-xs h-7">
            Retry
          </Button>
        </div>
      )}

      {/* Filters Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-card p-3 rounded-lg border border-border/60">
        <div className="flex flex-1 items-center gap-3 w-full sm:w-auto">
          <div className="relative flex-1 sm:w-80">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by email, name, provider ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 h-9 text-xs"
            />
          </div>
          <Select value={roleFilter} onValueChange={setRoleFilter}>
            <SelectTrigger className="w-32 h-9 text-xs">
              <SelectValue placeholder="Role" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Roles</SelectItem>
              <SelectItem value="admin">Superadmin</SelectItem>
              <SelectItem value="user">User</SelectItem>
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-32 h-9 text-xs">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="suspended">Suspended</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button variant="ghost" size="sm" onClick={fetchUsers} disabled={loading} className="gap-2 shrink-0">
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Users Table */}
      <Card className="border-border/60">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5 text-primary" />
              <span>Registered Accounts ({users.length})</span>
            </div>
            <Badge variant="secondary" className="text-xs">
              100% Real PostgreSQL Data
            </Badge>
          </CardTitle>
          <CardDescription>
            Live tenant registry with minute balances, call logs, and instant superadmin control actions.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-border/60 overflow-hidden">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow>
                  <TableHead className="text-xs">User / Email</TableHead>
                  <TableHead className="text-xs">Role</TableHead>
                  <TableHead className="text-xs">Organization</TableHead>
                  <TableHead className="text-xs">SaaS Plan</TableHead>
                  <TableHead className="text-xs text-center">Calls Made</TableHead>
                  <TableHead className="text-xs text-right">Wallet Balance</TableHead>
                  <TableHead className="text-xs text-center">Local CPU AI</TableHead>
                  <TableHead className="text-xs text-center">Status</TableHead>
                  <TableHead className="text-xs text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={9} className="text-center py-12 text-sm text-muted-foreground">
                      {loading ? (
                        <div className="flex items-center justify-center gap-2">
                          <Loader2 className="h-4 w-4 animate-spin text-primary" />
                          <span>Loading registered users from database...</span>
                        </div>
                      ) : (
                        <span>No users matching current filters found.</span>
                      )}
                    </TableCell>
                  </TableRow>
                ) : (
                  users.map((u) => {
                    const balance = u.wallet_balance_minutes ?? u.organization?.wallet_balance_minutes ?? 0;
                    return (
                      <TableRow key={u.id} className="hover:bg-muted/20">
                        <TableCell>
                          <div className="font-semibold text-xs flex items-center gap-1.5">
                            {u.email}
                          </div>
                          <div className="text-[11px] text-muted-foreground">
                            {u.name || `ID #${u.id}`} • {u.created_at ? new Date(u.created_at).toLocaleDateString() : ""}
                          </div>
                        </TableCell>
                        <TableCell>
                          {u.is_superuser ? (
                            <Badge className="bg-purple-500/10 text-purple-600 border-purple-500/20 text-[10px] gap-1">
                              <Shield className="h-3 w-3" /> Superadmin
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="text-[10px] text-muted-foreground">
                              User
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-xs font-medium">
                          {u.organization_name || u.organization?.name || `Org #${u.organization_id || u.organization?.id || "-"}`}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-[10px] uppercase font-semibold">
                            {u.plan_name || u.organization?.current_plan || "Starter"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-center">
                          <Badge variant="secondary" className="font-mono text-xs gap-1">
                            <PhoneCall className="h-3 w-3 text-muted-foreground" />
                            {u.total_calls ?? 0}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex flex-col items-end gap-0.5">
                            <span className="font-mono text-xs font-bold text-emerald-600 dark:text-emerald-400">
                              {balance.toFixed(1)} mins
                            </span>
                            {u.is_wallet_frozen && (
                              <Badge variant="destructive" className="text-[9px] py-0 px-1 leading-tight">
                                Wallet Frozen
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="text-center">
                          {u.has_local_ai_access ? (
                            <Badge className="bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30 text-[10px] gap-1 font-semibold">
                              <Sparkles className="h-2.5 w-2.5 text-amber-500" /> Active
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="text-[10px] text-muted-foreground opacity-60">
                              Disabled
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-center">
                          {u.is_active ? (
                            <Badge className="bg-emerald-500/10 text-emerald-600 border-emerald-500/20 text-[10px] gap-1">
                              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                              Active
                            </Badge>
                          ) : (
                            <Badge variant="destructive" className="text-[10px] gap-1">
                              <ShieldAlert className="h-3 w-3" /> Suspended
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon" className="h-7 w-7">
                                <MoreHorizontal className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-48 text-xs">
                              <DropdownMenuLabel>User Actions</DropdownMenuLabel>
                              <DropdownMenuItem
                                onClick={() => {
                                  setSelectedUser(u);
                                  setGrantMinutes(60);
                                  setGrantNote("Admin promotional credit");
                                  setGrantModalOpen(true);
                                }}
                              >
                                <Coins className="h-3.5 w-3.5 mr-2 text-amber-500" />
                                Grant Minutes
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                onClick={() => {
                                  setSelectedUser(u);
                                  setEditForm({
                                    is_superuser: Boolean(u.is_superuser),
                                    has_local_ai_access: Boolean(u.has_local_ai_access),
                                    is_wallet_frozen: Boolean(u.is_wallet_frozen),
                                    max_concurrent_calls: u.max_concurrent_calls ?? 2,
                                    max_agents: u.max_agents ?? 10,
                                    enable_campaigns: u.enable_campaigns ?? true,
                                    enable_crm: u.enable_crm ?? true,
                                    enable_widgets: u.enable_widgets ?? true,
                                    enable_appointments: u.enable_appointments ?? true,
                                    enable_forms: u.enable_forms ?? true,
                                    enable_byok: u.enable_byok ?? true,
                                    plan_name: u.plan_name || "Starter",
                                    wallet_balance_minutes: balance,
                                  });
                                  setEditModalOpen(true);
                                }}
                              >
                                <Edit className="h-3.5 w-3.5 mr-2 text-primary" />
                                Edit User & Plan
                              </DropdownMenuItem>

                              <DropdownMenuItem
                                onClick={() => {
                                  setSelectedUser(u);
                                  setNewPassword("");
                                  setPasswordModalOpen(true);
                                }}
                              >
                                <KeyRound className="h-3.5 w-3.5 mr-2 text-indigo-500" />
                                Reset Password
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => handleImpersonate(u)}>
                                <ExternalLink className="h-3.5 w-3.5 mr-2 text-blue-500" />
                                Login As User
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                onClick={() => handleToggleStatus(u)}
                                className={u.is_active ? "text-destructive" : "text-emerald-600"}
                              >
                                {u.is_active ? (
                                  <>
                                    <UserMinus className="h-3.5 w-3.5 mr-2" />
                                    Suspend Account
                                  </>
                                ) : (
                                  <>
                                    <UserCheck className="h-3.5 w-3.5 mr-2" />
                                    Reactivate Account
                                  </>
                                )}
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                onClick={() => {
                                  setSelectedUser(u);
                                  setDeleteModalOpen(true);
                                }}
                                className="text-destructive font-semibold"
                              >
                                <Trash2 className="h-3.5 w-3.5 mr-2" />
                                Delete User
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
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

      {/* 1. CREATE USER MODAL */}
      <Dialog open={createModalOpen} onOpenChange={setCreateModalOpen}>
        <DialogContent className="sm:max-w-md">
          <form onSubmit={handleCreateUser}>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <UserPlus className="h-5 w-5 text-primary" />
                Provision New User Account
              </DialogTitle>
              <DialogDescription>
                Create a tenant account directly from the sovereign admin console with custom plan and minute allocation.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4 text-xs">
              <div className="space-y-1.5">
                <Label className="text-xs">Email Address *</Label>
                <Input
                  type="email"
                  required
                  placeholder="user@company.com"
                  value={createForm.email}
                  onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Password *</Label>
                <Input
                  type="password"
                  required
                  placeholder="Minimum 4 characters"
                  value={createForm.password}
                  onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Full Name / Organization (Optional)</Label>
                <Input
                  placeholder="Acme Corp / John Doe"
                  value={createForm.name}
                  onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">SaaS Plan</Label>
                  <Select
                    value={createForm.plan_code}
                    onValueChange={(val) => setCreateForm({ ...createForm, plan_code: val })}
                  >
                    <SelectTrigger className="h-9 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="starter">Starter (60m)</SelectItem>
                      <SelectItem value="pro">Pro (300m)</SelectItem>
                      <SelectItem value="enterprise">Enterprise (Custom)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Initial Minutes</Label>
                  <Input
                    type="number"
                    min={0}
                    value={createForm.initial_minutes}
                    onChange={(e) => setCreateForm({ ...createForm, initial_minutes: parseInt(e.target.value) || 0 })}
                  />
                </div>
              </div>
              <div className="flex items-center gap-2 pt-2">
                <input
                  type="checkbox"
                  id="create-superadmin"
                  checked={createForm.is_superuser}
                  onChange={(e) => setCreateForm({ ...createForm, is_superuser: e.target.checked })}
                  className="rounded border-border text-primary focus:ring-primary"
                />
                <Label htmlFor="create-superadmin" className="text-xs font-medium cursor-pointer">
                  Grant Superadmin Access
                </Label>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="create-local-ai"
                  checked={createForm.has_local_ai_access}
                  onChange={(e) => setCreateForm({ ...createForm, has_local_ai_access: e.target.checked })}
                  className="rounded border-border text-primary focus:ring-primary"
                />
                <Label htmlFor="create-local-ai" className="text-xs font-medium cursor-pointer">
                  Allow Local AI Access (Self-Hosted CPU Engine)
                </Label>
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" size="sm" onClick={() => setCreateModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={actionLoading}>
                {actionLoading && <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" />}
                Create Account
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* 2. GRANT MINUTES MODAL */}
      <Dialog open={grantModalOpen} onOpenChange={setGrantModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Coins className="h-5 w-5 text-amber-500" />
              Grant Sovereign Voice Minutes
            </DialogTitle>
            <DialogDescription>
              Award instant promotional voice minutes to {selectedUser?.email}. Recorded permanently in ledger.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4 text-xs">
            <div className="space-y-1.5">
              <Label className="text-xs">Preset Packages</Label>
              <div className="grid grid-cols-4 gap-2">
                {[30, 60, 120, 500].map((m) => (
                  <Button
                    key={m}
                    type="button"
                    variant={grantMinutes === m ? "default" : "outline"}
                    size="sm"
                    className="h-8 text-xs font-semibold"
                    onClick={() => setGrantMinutes(m)}
                  >
                    +{m}m
                  </Button>
                ))}
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Custom Minutes</Label>
              <Input
                type="number"
                min={1}
                value={grantMinutes}
                onChange={(e) => setGrantMinutes(parseInt(e.target.value) || 0)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Reason / Audit Note</Label>
              <Input
                value={grantNote}
                onChange={(e) => setGrantNote(e.target.value)}
                placeholder="e.g. Compensation, Promotional onboarding credit"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setGrantModalOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleGrantMinutes} disabled={actionLoading || grantMinutes <= 0}>
              {actionLoading && <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" />}
              Grant {grantMinutes} Minutes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 3. EDIT USER MODAL - FULL SUPERADMIN WORKSPACE CONTROLS */}
      <Dialog open={editModalOpen} onOpenChange={setEditModalOpen}>
        <DialogContent className="sm:max-w-xl max-h-[85vh] overflow-y-auto">
          <form onSubmit={handleEditUser}>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2 text-base font-bold">
                <Edit className="h-5 w-5 text-primary" />
                Superadmin Workspace Control & Entitlements
              </DialogTitle>
              <DialogDescription className="text-xs">
                Manage quotas, module access, security locks, and billing overrides for <span className="font-semibold text-foreground">{selectedUser?.email}</span>.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-5 py-4 text-xs">
              {/* Emergency Wallet Freeze Switch */}
              <div className="p-3 rounded-lg border border-destructive/30 bg-destructive/5 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <ShieldAlert className="h-4 w-4 text-destructive" />
                    <span className="font-semibold text-destructive text-xs">Emergency Wallet Freeze</span>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editForm.is_wallet_frozen}
                      onChange={(e) => setEditForm({ ...editForm, is_wallet_frozen: e.target.checked })}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-destructive"></div>
                  </label>
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  When frozen, all outbound telephone calls, web audio runs, and campaigns from this workspace are instantly blocked.
                </p>
              </div>

              {/* Plan & Minute Overrides */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 rounded-lg border bg-muted/20">
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium">SaaS Subscription Plan</Label>
                  <Select
                    value={editForm.plan_name}
                    onValueChange={(val) => setEditForm({ ...editForm, plan_name: val })}
                  >
                    <SelectTrigger className="h-9 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Starter">Starter Plan</SelectItem>
                      <SelectItem value="Pro">Pro Plan</SelectItem>
                      <SelectItem value="Enterprise">Enterprise Plan</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium">Wallet Minute Balance (Override)</Label>
                  <Input
                    type="number"
                    min={0}
                    className="h-9 text-xs"
                    value={editForm.wallet_balance_minutes}
                    onChange={(e) => setEditForm({ ...editForm, wallet_balance_minutes: parseInt(e.target.value) || 0 })}
                  />
                </div>
              </div>

              {/* Resource Quotas */}
              <div className="p-3 rounded-lg border space-y-3">
                <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                  <PhoneCall className="h-3.5 w-3.5 text-primary" />
                  Tenant Resource Quotas
                </h4>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-[11px] text-muted-foreground">Max Concurrent Calls</Label>
                    <Input
                      type="number"
                      min={1}
                      max={100}
                      className="h-8 text-xs font-mono"
                      value={editForm.max_concurrent_calls}
                      onChange={(e) => setEditForm({ ...editForm, max_concurrent_calls: parseInt(e.target.value) || 1 })}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-[11px] text-muted-foreground">Max Voice Agents</Label>
                    <Input
                      type="number"
                      min={1}
                      max={200}
                      className="h-8 text-xs font-mono"
                      value={editForm.max_agents}
                      onChange={(e) => setEditForm({ ...editForm, max_agents: parseInt(e.target.value) || 1 })}
                    />
                  </div>
                </div>
              </div>

              {/* Module Feature Flags */}
              <div className="p-3 rounded-lg border space-y-3">
                <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                  <Shield className="h-3.5 w-3.5 text-primary" />
                  Module Feature Flags & Tenant Permissions
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  <label className="flex items-center gap-2 p-2 rounded border bg-card/50 cursor-pointer hover:bg-muted/40 transition-colors">
                    <input
                      type="checkbox"
                      checked={editForm.enable_crm}
                      onChange={(e) => setEditForm({ ...editForm, enable_crm: e.target.checked })}
                      className="rounded border-border text-primary focus:ring-primary"
                    />
                    <div>
                      <div className="font-semibold text-xs">CRM Leads Module</div>
                      <div className="text-[10px] text-muted-foreground">Contacts & pipeline tracking</div>
                    </div>
                  </label>

                  <label className="flex items-center gap-2 p-2 rounded border bg-card/50 cursor-pointer hover:bg-muted/40 transition-colors">
                    <input
                      type="checkbox"
                      checked={editForm.enable_campaigns}
                      onChange={(e) => setEditForm({ ...editForm, enable_campaigns: e.target.checked })}
                      className="rounded border-border text-primary focus:ring-primary"
                    />
                    <div>
                      <div className="font-semibold text-xs">Outbound Campaigns</div>
                      <div className="text-[10px] text-muted-foreground">Batch voice calling dialer</div>
                    </div>
                  </label>

                  <label className="flex items-center gap-2 p-2 rounded border bg-card/50 cursor-pointer hover:bg-muted/40 transition-colors">
                    <input
                      type="checkbox"
                      checked={editForm.enable_widgets}
                      onChange={(e) => setEditForm({ ...editForm, enable_widgets: e.target.checked })}
                      className="rounded border-border text-primary focus:ring-primary"
                    />
                    <div>
                      <div className="font-semibold text-xs">Web Call Widgets</div>
                      <div className="text-[10px] text-muted-foreground">Embeddable website voice button</div>
                    </div>
                  </label>

                  <label className="flex items-center gap-2 p-2 rounded border bg-card/50 cursor-pointer hover:bg-muted/40 transition-colors">
                    <input
                      type="checkbox"
                      checked={editForm.enable_appointments}
                      onChange={(e) => setEditForm({ ...editForm, enable_appointments: e.target.checked })}
                      className="rounded border-border text-primary focus:ring-primary"
                    />
                    <div>
                      <div className="font-semibold text-xs">Appointments Booking</div>
                      <div className="text-[10px] text-muted-foreground">Calendar integrations</div>
                    </div>
                  </label>

                  <label className="flex items-center gap-2 p-2 rounded border bg-card/50 cursor-pointer hover:bg-muted/40 transition-colors">
                    <input
                      type="checkbox"
                      checked={editForm.enable_forms}
                      onChange={(e) => setEditForm({ ...editForm, enable_forms: e.target.checked })}
                      className="rounded border-border text-primary focus:ring-primary"
                    />
                    <div>
                      <div className="font-semibold text-xs">Dynamic Voice Forms</div>
                      <div className="text-[10px] text-muted-foreground">Form collection over voice</div>
                    </div>
                  </label>

                  <label className="flex items-center gap-2 p-2 rounded border bg-card/50 cursor-pointer hover:bg-muted/40 transition-colors">
                    <input
                      type="checkbox"
                      checked={editForm.enable_byok}
                      onChange={(e) => setEditForm({ ...editForm, enable_byok: e.target.checked })}
                      className="rounded border-border text-primary focus:ring-primary"
                    />
                    <div>
                      <div className="font-semibold text-xs">Bring Your Own Key (BYOK)</div>
                      <div className="text-[10px] text-muted-foreground">Custom provider API keys</div>
                    </div>
                  </label>
                </div>
              </div>

              {/* Special Permissions */}
              <div className="space-y-2 p-3 rounded-lg border bg-muted/10">
                <h4 className="text-xs font-bold text-foreground">Special Privileges</h4>
                <div className="flex flex-col gap-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      id="edit-superadmin"
                      checked={editForm.is_superuser}
                      onChange={(e) => setEditForm({ ...editForm, is_superuser: e.target.checked })}
                      className="rounded border-border text-primary focus:ring-primary"
                    />
                    <div>
                      <span className="text-xs font-semibold">Superadmin Privileges</span>
                      <p className="text-[10px] text-muted-foreground">Access all tenants, server settings, and master key management.</p>
                    </div>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer pt-1">
                    <input
                      type="checkbox"
                      id="edit-local-ai"
                      checked={editForm.has_local_ai_access}
                      onChange={(e) => setEditForm({ ...editForm, has_local_ai_access: e.target.checked })}
                      className="rounded border-border text-primary focus:ring-primary"
                    />
                    <div>
                      <span className="text-xs font-semibold text-amber-500">Allow Local CPU AI Access (Ollama + Speaches)</span>
                      <p className="text-[10px] text-muted-foreground">Enables 100% free self-hosted sovereign CPU models for this user.</p>
                    </div>
                  </label>
                </div>
              </div>
            </div>

            <DialogFooter className="gap-2 sm:gap-0 pt-2 border-t">
              <Button type="button" variant="outline" size="sm" onClick={() => setEditModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={actionLoading}>
                {actionLoading && <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" />}
                Save Changes
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* 4. RESET PASSWORD MODAL */}
      <Dialog open={passwordModalOpen} onOpenChange={setPasswordModalOpen}>
        <DialogContent className="sm:max-w-md">
          <form onSubmit={handleResetPassword}>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <KeyRound className="h-5 w-5 text-indigo-500" />
                Reset User Password
              </DialogTitle>
              <DialogDescription>
                Set a new password for {selectedUser?.email}. The user can log in immediately with this password.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4 text-xs">
              <div className="space-y-1.5">
                <Label className="text-xs">New Password *</Label>
                <Input
                  type="password"
                  required
                  placeholder="Minimum 4 characters"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" size="sm" onClick={() => setPasswordModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={actionLoading || !newPassword}>
                {actionLoading && <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" />}
                Update Password
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* 5. DELETE USER CONFIRM MODAL */}
      <Dialog open={deleteModalOpen} onOpenChange={setDeleteModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <Trash2 className="h-5 w-5" />
              Permanently Delete User
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to permanently delete account <strong>{selectedUser?.email}</strong>? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" size="sm" onClick={() => setDeleteModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" size="sm" onClick={handleDeleteUser} disabled={actionLoading}>
              {actionLoading && <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" />}
              Confirm Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
