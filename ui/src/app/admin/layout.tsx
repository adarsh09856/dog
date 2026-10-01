"use client";

import {
  Activity,
  ArrowLeft,
  Coins,
  Cpu,
  FileSpreadsheet,
  FileText,
  KeyRound,
  LayoutDashboard,
  LogOut,
  PhoneCall,
  Radio,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import React from "react";

import ThemeToggle from "@/components/ThemeSwitcher";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const ADMIN_NAV = [
  { title: "Dashboard", href: "/admin", icon: LayoutDashboard },
  { title: "Master Keys & Models", href: "/admin/models", icon: Cpu },
  { title: "User Management", href: "/admin/users", icon: Users },
  { title: "SaaS Plans", href: "/admin/plans", icon: FileSpreadsheet },
  { title: "Credit Bundles", href: "/admin/credit-packages", icon: Coins },
  { title: "Live Call Monitor", href: "/admin/monitoring", icon: Radio },
  { title: "Global Call History", href: "/superuser/workflow-runs", icon: PhoneCall },
  { title: "Content Moderation", href: "/admin/moderation", icon: ShieldAlert },
  { title: "Platform Settings", href: "/admin/settings", icon: Settings },
  { title: "Audit Trail", href: "/admin/audit-logs", icon: FileText },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, isAuthenticated, loading } = useAuth();

  const isSuper = (user as any)?.is_superuser || (user as any)?.role === 'admin' || (user as any)?.is_admin;

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background text-foreground">
        <Activity className="h-6 w-6 animate-spin text-primary" />
        <span className="ml-2 text-sm text-muted-foreground">Verifying Superadmin privileges...</span>
      </div>
    );
  }

  // If not authenticated, redirect to login
  if (!isAuthenticated) {
    if (typeof window !== 'undefined') {
      window.location.href = '/auth/login';
    }
    return (
      <div className="flex h-screen items-center justify-center bg-background text-foreground">
        <Activity className="h-6 w-6 animate-spin text-primary" />
        <span className="ml-2 text-sm text-muted-foreground">Redirecting to login...</span>
      </div>
    );
  }

  // If user is authenticated but not superuser, warn them
  if (isAuthenticated && !isSuper) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-background p-6 text-center">
        <ShieldAlert className="h-12 w-12 text-destructive mb-4" />
        <h1 className="text-2xl font-bold tracking-tight">Superadmin Access Required</h1>
        <p className="mt-2 text-sm text-muted-foreground max-w-md">
          Your account ({user?.email}) does not have administrative privileges to access the Kodewaves sovereign control plane.
        </p>
        <div className="mt-6 flex gap-4">
          <Button variant="outline" onClick={() => router.push("/workflow")}>
            Back to App
          </Button>
          <Button variant="destructive" onClick={() => logout()}>
            Sign Out
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-muted/20 text-foreground">
      {/* Admin Sidebar */}
      <aside className="w-64 border-r border-border/60 bg-card flex flex-col shrink-0">
        <div className="flex items-center gap-3 px-5 py-4 border-b border-border/40">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground font-black shadow-md">
            KW
          </div>
          <div>
            <div className="text-sm font-bold tracking-tight">Kodewaves Admin</div>
            <div className="text-[10px] uppercase font-semibold text-emerald-500 flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Sovereign Control
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-1 p-3 overflow-y-auto">
          <div className="px-3 py-1.5 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
            Management
          </div>
          {ADMIN_NAV.map((item) => {
            const isActive = pathname === item.href || (item.href !== "/admin" && pathname.startsWith(item.href));
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-xs font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground font-semibold shadow-sm"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground"
                )}
              >
                <Icon className={cn("h-4 w-4", isActive ? "text-primary-foreground" : "text-muted-foreground")} />
                {item.title}
              </Link>
            );
          })}
        </nav>

        <div className="p-3 border-t border-border/40 space-y-2">
          <Link
            href="/workflow"
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Exit to Voice Studio
          </Link>
          <div className="flex items-center justify-between px-3 py-2 bg-muted/40 rounded-lg">
            <span className="text-xs truncate max-w-[140px] text-muted-foreground">
              {user?.email || "Superadmin"}
            </span>
            <div className="flex items-center gap-1">
              <ThemeToggle showLabel={false} />
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-muted-foreground hover:text-destructive"
                onClick={() => logout()}
                title="Sign out"
              >
                <LogOut className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-7xl mx-auto p-6 md:p-8">
          {children}
        </div>
      </main>
    </div>
  );
}
