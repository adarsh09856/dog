"use client";

import { AlertTriangle, Menu, RefreshCw } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import React, { ReactNode } from "react";

import { BrandLogo } from "@/components/BrandLogo";
import { Button } from "@/components/ui/button";
import { SidebarInset, SidebarProvider, useSidebar } from "@/components/ui/sidebar";
import { useAppConfig } from "@/context/AppConfigContext";
import { useClientEntitlements } from "@/context/ClientEntitlementsContext";
import { LeadFormsProvider } from "@/context/LeadFormsContext";
import { useAuth } from "@/lib/auth";
import { requiredFeatureForUiPath } from "@/lib/clientEntitlements";

import { AppSidebar } from "./AppSidebar";

function AppHeader() {
  const { toggleSidebar } = useSidebar();
  const pathname = usePathname();
  const section = (pathname || "/").split("/").filter(Boolean)[0] || "Workspace";
  const sectionLabel = section === "workflow" ? "Voice agents" : section.replaceAll("-", " ");

  return (
    <header className="workspace-topbar sticky top-[var(--event-banner-h,0px)] z-50 flex items-center justify-between border-b border-border/60 bg-background/70 px-4 py-2 backdrop-blur-md supports-[backdrop-filter]:bg-background/55">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={toggleSidebar} aria-label="Open menu" className="md:hidden">
          <Menu className="h-5 w-5" />
        </Button>
        <Link href="/" className="md:hidden" aria-label="Home"><BrandLogo className="h-6" /></Link>
        <div className="hidden items-center gap-3 text-xs md:flex"><span className="text-muted-foreground">Workspace</span><span aria-hidden="true" className="text-muted-foreground/50">/</span><span className="font-semibold capitalize text-foreground">{sectionLabel}</span></div>
      </div>
      <span className="hidden font-mono text-[9px] tracking-[.12em] text-muted-foreground sm:inline">VOICE OPERATIONS</span>
    </header>
  );
}

function BackendStatusBanner() {
  const { config, loading, refresh } = useAppConfig();
  const pathname = usePathname();

  if (
    !config ||
    config.backendStatus === "reachable" ||
    pathname === "/" ||
    pathname?.startsWith("/auth") ||
    pathname?.startsWith("/pricing") ||
    pathname?.startsWith("/embed") ||
    pathname?.startsWith("/admin") ||
    pathname?.startsWith("/superadmin")
  ) {
    return null;
  }

  const backendUrl = config.backendUrl && config.backendUrl !== "unknown"
    ? config.backendUrl
    : "the configured backend";
  const message = config.backendMessage || `Backend is not reachable at ${backendUrl}.`;

  return (
    <div
      role="alert"
      className="border-b border-amber-300 bg-amber-50 px-4 py-3 text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-100"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-semibold">Backend connection failed</p>
            <p className="break-words text-sm">{message}</p>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void refresh()}
          disabled={loading}
          className="h-8 shrink-0 border-amber-400 bg-transparent text-amber-950 hover:bg-amber-100 dark:border-amber-700 dark:text-amber-100 dark:hover:bg-amber-900/40"
        >
          <RefreshCw className="h-4 w-4" />
          Retry
        </Button>
      </div>
    </div>
  );
}

interface AppLayoutProps {
  children: ReactNode;
  headerActions?: ReactNode;
  stickyTabs?: ReactNode;
}

const AppLayout: React.FC<AppLayoutProps> = ({
  children,
  headerActions,
  stickyTabs,
}) => {
  const pathname = usePathname();
  const { isAuthenticated } = useAuth();
  const entitlements = useClientEntitlements();
  const requiredFeature = requiredFeatureForUiPath(pathname);

  // Public marketing & embedding routes: Never render sidebar or internal app chrome
  const isPublicOrMarketing =
    pathname === "/" ||
    pathname.startsWith("/pricing") ||
    pathname.startsWith("/auth") ||
    pathname.startsWith("/handler") ||
    pathname.startsWith("/embed");

  // Admin and superadmin control plane routes have their own layout and sidebar
  const isAdminRoute =
    pathname.startsWith("/admin") ||
    pathname.startsWith("/superadmin") ||
    pathname.startsWith("/superuser");

  // Show AppSidebar only on authenticated private tenant application routes
  const shouldShowSidebar = Boolean(isAuthenticated && !isPublicOrMarketing && !isAdminRoute);

  // Only match the exact editor page /workflow/<id>, not sub-routes like /workflow/<id>/runs
  const isWorkflowEditor = /^\/workflow\/\d+$/.test(pathname);

  // Always render SidebarProvider to keep the component tree shape consistent
  // across route changes (avoids React hooks ordering violations during navigation).
  return (
    <SidebarProvider defaultOpen>
      {shouldShowSidebar ? (
        <LeadFormsProvider>
          <div className="flex min-h-screen w-full">
            <AppSidebar />
            <SidebarInset className="flex-1">
              <BackendStatusBanner />
              {!isWorkflowEditor && <AppHeader />}
              {/* Optional header area for specific pages */}
              {headerActions && (
                <header className="sticky top-[var(--event-banner-h,0px)] z-50 w-full border-b border-border/60 bg-background/70 backdrop-blur-md supports-[backdrop-filter]:bg-background/55">
                  <div className="container mx-auto px-4 py-4">
                    <div className="flex items-center justify-center">
                      {headerActions}
                    </div>
                  </div>
                </header>
              )}

              {/* Optional sticky tabs */}
              {stickyTabs && (
                <div className="sticky top-[var(--event-banner-h,0px)] z-40 bg-background border-b border-border text-foreground">
                  <div className="container mx-auto px-4">
                    <div className="flex items-center justify-center py-2">
                      {stickyTabs}
                    </div>
                  </div>
                </div>
              )}

              {/* Main content area */}
              <main className="app-surface flex-1">
                {entitlements.isClientEdition && requiredFeature && entitlements.loading ? (
                  <div className="container mx-auto px-4 py-12" role="status" aria-live="polite">
                    Checking installation access…
                  </div>
                ) : entitlements.isClientEdition && requiredFeature && !entitlements.hasFeature(requiredFeature) ? (
                  <section className="container mx-auto max-w-2xl px-4 py-16">
                    <div className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm">
                      <h1 className="text-xl font-semibold">{entitlements.valid === true ? "Feature unavailable" : "Installation access unavailable"}</h1>
                      <p className="mt-2 text-sm text-muted-foreground">
                        {entitlements.valid !== true
                          ? entitlements.message || "The installation license could not be verified."
                          : `This installation does not include the ${requiredFeature.replaceAll("_", " ")} feature.`}
                        {" "}{entitlements.valid === true ? "Contact your platform owner to update the license." : "Try again or contact your platform owner."}
                      </p>
                      {entitlements.valid !== true && (
                        <Button type="button" variant="outline" className="mt-5 mr-4" onClick={() => void entitlements.refresh()}>
                          Retry
                        </Button>
                      )}
                      <Link href="/settings" className="mt-5 inline-flex text-sm font-medium text-primary underline-offset-4 hover:underline">
                        View installation status
                      </Link>
                    </div>
                  </section>
                ) : children}
              </main>
            </SidebarInset>
          </div>
        </LeadFormsProvider>
      ) : (
        <div className="app-surface w-full flex-1">
          <BackendStatusBanner />
          {children}
        </div>
      )}
    </SidebarProvider>
  );
};

export default AppLayout;
