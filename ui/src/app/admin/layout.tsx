"use client";

import {
  Activity,
  ArrowLeft,
  Coins,
  Cpu,
  FileSpreadsheet,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  PackageCheck,
  PhoneCall,
  Radio,
  Settings,
  ShieldAlert,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import React, { useEffect, useState } from "react";

import { BrandLogo } from "@/components/BrandLogo";
import panel from "@/components/layout/PanelWorkspace.module.css";
import ThemeToggle from "@/components/ThemeSwitcher";
import { Button } from "@/components/ui/button";
import { useClientBranding } from "@/context/ClientBrandingContext";
import { useAuth } from "@/lib/auth";
import { getUserEmail } from "@/lib/auth/userDisplay";
import { apiFetch } from "@/lib/kodewavesApi";
import { cn } from "@/lib/utils";

import chrome from "./AdminChrome.module.css";

const ADMIN_NAV = [
  { section: "Overview", title: "Dashboard", href: "/admin", icon: LayoutDashboard },
  { section: "Access & commercial", title: "Master Keys & Models", href: "/admin/models", icon: Cpu },
  { section: "Access & commercial", title: "User Management", href: "/admin/users", icon: Users },
  { section: "Access & commercial", title: "SaaS Plans", href: "/admin/plans", icon: FileSpreadsheet },
  { section: "Access & commercial", title: "Client Installations", href: "/admin/client-installations", icon: PackageCheck },
  { section: "Access & commercial", title: "Credit Bundles", href: "/admin/credit-packages", icon: Coins },
  { section: "Operations", title: "Live Call Monitor", href: "/admin/monitoring", icon: Radio },
  { section: "Operations", title: "Global Call History", href: "/superadmin/runs", icon: PhoneCall },
  { section: "Operations", title: "Content Moderation", href: "/admin/moderation", icon: ShieldAlert },
  { section: "Operations", title: "Platform Settings", href: "/admin/settings", icon: Settings },
  { section: "Operations", title: "Audit Trail", href: "/admin/audit-logs", icon: FileText },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const branding = useClientBranding();
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, isAuthenticated, loading } = useAuth();

  const isSuper = user?.is_superuser === true;
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [integrityAlertCount, setIntegrityAlertCount] = useState(0);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (loading || !isSuper) return;
    let active = true;
    const refreshAlerts = () => {
      void apiFetch<{ id: number }[]>("/admin/client-installations/alerts")
        .then((alerts) => { if (active) setIntegrityAlertCount(alerts.length); })
        .catch(() => { /* The installations page shows request errors and supports retry. */ });
    };
    refreshAlerts();
    const interval = window.setInterval(refreshAlerts, 60_000);
    window.addEventListener("focus", refreshAlerts);
    window.addEventListener("kodewaves-integrity-alerts-changed", refreshAlerts);
    return () => {
      active = false;
      window.clearInterval(interval);
      window.removeEventListener("focus", refreshAlerts);
      window.removeEventListener("kodewaves-integrity-alerts-changed", refreshAlerts);
    };
  }, [isSuper, loading]);

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
          Your account ({getUserEmail(user)}) does not have administrative privileges to access the {branding.company_name} control panel.
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
    <div className={`${panel.adminShell} ${chrome.shell} flex min-h-screen bg-muted/20 text-foreground`}>
      {mobileNavOpen && (
        <button
          type="button"
          aria-label="Close admin navigation overlay"
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setMobileNavOpen(false)}
        />
      )}

      {/* Admin Sidebar */}
      <aside
        id="admin-navigation"
        className={cn(
          `${panel.adminNavigation} ${chrome.navigation} invisible fixed inset-y-0 left-0 z-50 flex w-64 max-w-[85vw] shrink-0 flex-col border-r border-border/60 bg-card transition-transform duration-200 md:visible md:static md:z-auto md:max-w-none md:translate-x-0`,
          mobileNavOpen ? "visible translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex items-center gap-3 px-5 py-4 border-b border-border/40">
          <BrandLogo mark className="h-9" />
          <div>
            <div className="text-sm font-bold tracking-tight">{branding.company_name} Admin</div>
            <div className="text-[10px] uppercase font-semibold tracking-[0.14em] text-muted-foreground">
              Platform owner
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-1 p-3 overflow-y-auto">
          {ADMIN_NAV.map((item, index) => {
            const isActive = pathname === item.href || (item.href !== "/admin" && pathname.startsWith(item.href));
            const Icon = item.icon;
            return (
              <React.Fragment key={item.href}>
                {index === 0 || ADMIN_NAV[index - 1].section !== item.section ? (
                  <div className={cn("px-3 pb-1 pt-5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground", index === 0 && "pt-1")}>
                    {item.section}
                  </div>
                ) : null}
                <Link
                  href={item.href}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded-md border-l-2 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "border-primary bg-primary/10 pl-[10px] text-foreground"
                      : "border-transparent pl-[10px] text-muted-foreground hover:bg-accent hover:text-foreground"
                  )}
                  onClick={() => setMobileNavOpen(false)}
                >
                  <Icon className={cn("h-4 w-4", isActive ? "text-primary" : "text-muted-foreground")} />
                  {item.title}
                  {item.href === "/admin/client-installations" && integrityAlertCount > 0 && <span className="ml-auto rounded-full bg-destructive px-1.5 py-0.5 text-[10px] font-bold text-destructive-foreground" aria-label={`${integrityAlertCount} installation integrity alerts`}>{integrityAlertCount}</span>}
                </Link>
              </React.Fragment>
            );
          })}
        </nav>

        <div className={`${chrome.footer} p-3 border-t border-border/40 space-y-2`}>
          <Link
            href="/workflow"
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            onClick={() => setMobileNavOpen(false)}
          >
            <ArrowLeft className="h-4 w-4" />
            Exit to Voice Studio
          </Link>
          <div className="flex items-center justify-between px-3 py-2 bg-muted/40 rounded-lg">
            <span className="text-xs truncate max-w-[140px] text-muted-foreground">
              {getUserEmail(user) || "Superadmin"}
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
      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className={`${chrome.mobileBar} sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border/60 bg-card/95 px-4 backdrop-blur md:hidden`}>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={mobileNavOpen ? "Close admin navigation" : "Open admin navigation"}
            aria-expanded={mobileNavOpen}
            aria-controls="admin-navigation"
            onClick={() => setMobileNavOpen((open) => !open)}
          >
            {mobileNavOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </Button>
          <div className="flex min-w-0 items-center gap-2">
            <BrandLogo mark className="h-7" />
            <span className="truncate text-sm font-semibold">{branding.company_name} Admin</span>
          </div>
          <ThemeToggle showLabel={false} />
        </div>
        <div className={`${chrome.content} mx-auto max-w-7xl p-4 sm:p-6 md:p-8`}>
          {children}
        </div>
      </main>
    </div>
  );
}
