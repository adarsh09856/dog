"use client";

import {
  Activity,
  ArrowLeft,
  AudioLines,
  CalendarDays,
  FileText,
  Headphones,
  LayoutDashboard,
  Megaphone,
  Settings,
  ShieldAlert,
  Sparkles,
  Users,
  Workflow,
  Wrench,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { BrandLogo } from "@/components/BrandLogo";
import { Button } from "@/components/ui/button";
import { useClientBranding } from "@/context/ClientBrandingContext";
import { useClientEntitlements } from "@/context/ClientEntitlementsContext";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const ADMIN_LINKS = [
  { title: "Home", href: "/admin", icon: LayoutDashboard },
  { title: "CRM", href: "/crm", icon: Users, feature: "crm" },
  { title: "Voice agents", href: "/workflow", icon: Workflow, feature: "voice" },
  { title: "Campaigns", href: "/campaigns", icon: Megaphone, feature: "campaigns" },
  { title: "Appointments", href: "/appointments", icon: CalendarDays, feature: "appointments" },
  { title: "Voice forms", href: "/forms", icon: FileText, feature: "forms" },
  { title: "AI models", href: "/model-configurations", icon: Sparkles, feature: "models" },
  { title: "Tools", href: "/tools", icon: Wrench, feature: "tools" },
  { title: "Knowledge base", href: "/files", icon: FileText, feature: "knowledge_base" },
  { title: "Recordings", href: "/recordings", icon: AudioLines, feature: "recordings" },
  { title: "Usage & reports", href: "/usage", icon: Headphones, feature: "reports" },
  { title: "Workspace settings", href: "/settings", icon: Settings },
] as const;

export default function WorkspaceAdminLayout({ children }: { children: React.ReactNode }) {
  const branding = useClientBranding();
  const pathname = usePathname();
  const router = useRouter();
  const { user, isAuthenticated, loading, logout } = useAuth();
  const { hasFeature, isClientEdition, loading: entitlementsLoading } = useClientEntitlements();
  const isClientAdmin = isClientEdition && user?.is_superuser === true;
  const canManage = !isClientEdition || isClientAdmin;

  useEffect(() => {
    if (!loading && !isAuthenticated) router.replace(`/auth/login?redirect=${encodeURIComponent(pathname || "/admin")}`);
  }, [isAuthenticated, loading, pathname, router]);

  if (loading || (isClientEdition && entitlementsLoading)) {
    return <div className="flex min-h-screen items-center justify-center gap-3 text-muted-foreground"><Activity className="h-5 w-5 animate-spin" />Loading workspace administration…</div>;
  }

  if (!isAuthenticated) {
    return <div className="flex min-h-screen items-center justify-center text-muted-foreground">Redirecting to sign in…</div>;
  }

  if (!canManage) {
    return <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-6 text-center">
      <ShieldAlert className="mb-4 h-10 w-10 text-destructive" />
      <h1 className="text-2xl font-semibold tracking-tight">Administrator access required</h1>
      <p className="mt-2 text-sm text-muted-foreground">Ask your installation administrator to grant access to workspace controls.</p>
      <Button className="mt-6" variant="outline" onClick={() => router.push("/overview")}>Back to workspace</Button>
    </main>;
  }

  return <div className="min-h-screen bg-background text-foreground lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
    <aside className="border-b border-border/70 bg-sidebar lg:sticky lg:top-0 lg:h-screen lg:border-b-0 lg:border-r">
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between gap-3 border-b border-border/60 px-5 py-4">
          <Link href="/admin" className="flex min-w-0 items-center gap-3" aria-label={`${branding.company_name} workspace admin`}>
            <BrandLogo mark className="h-9 shrink-0" />
            <span className="min-w-0 truncate text-sm font-semibold">{branding.company_name}</span>
          </Link>
          <span className="hidden rounded-full border border-border px-2 py-1 text-[10px] text-muted-foreground sm:inline">ADMIN</span>
        </div>
        <nav aria-label="Workspace administration" className="grid grid-cols-2 gap-1 p-3 sm:grid-cols-3 lg:flex lg:flex-1 lg:flex-col lg:overflow-y-auto">
          {ADMIN_LINKS.filter((item) => !("feature" in item) || !item.feature || !isClientEdition || hasFeature(item.feature)).map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href || (item.href !== "/admin" && pathname.startsWith(`${item.href}/`));
            return <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} className={cn(
              "flex min-h-10 items-center gap-2 rounded-md px-3 text-xs font-medium text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active && "bg-sidebar-accent text-sidebar-accent-foreground",
            )}>
              <Icon className="h-4 w-4 shrink-0" />{item.title}
            </Link>;
          })}
          {!isClientEdition && user?.is_superuser === true && <Link href="/superadmin" className="flex min-h-10 items-center gap-2 rounded-md px-3 text-xs font-medium text-primary transition-colors hover:bg-sidebar-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <ShieldAlert className="h-4 w-4 shrink-0" />Superadmin
          </Link>}
        </nav>
        <div className="hidden border-t border-border/60 p-3 lg:block">
          <Button variant="ghost" className="w-full justify-start gap-2 text-xs" onClick={() => router.push("/overview")}>
            <ArrowLeft className="h-4 w-4" />Back to workspace
          </Button>
          <Button variant="ghost" className="mt-1 w-full justify-start gap-2 text-xs text-muted-foreground" onClick={() => void logout()}>
            Sign out
          </Button>
        </div>
      </div>
    </aside>
    <div className="min-w-0">
      <header className="sticky top-0 z-20 flex h-12 items-center justify-between border-b border-border/70 bg-background/95 px-4 backdrop-blur-sm lg:px-8">
        <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-xs text-muted-foreground"><Link href="/overview" className="hover:text-foreground">Workspace</Link><span aria-hidden="true">/</span><span className="font-medium capitalize text-foreground">{pathname === "/admin" ? "Admin" : pathname.split("/").filter(Boolean).at(-1)?.replaceAll("-", " ")}</span></nav>
        <span className="hidden text-[10px] font-medium tracking-[.12em] text-muted-foreground sm:inline">WORKSPACE CONTROLS</span>
      </header>
      <main className="mx-auto w-full max-w-[1440px] px-5 py-7 sm:px-8 lg:px-10">{children}</main>
    </div>
  </div>;
}
