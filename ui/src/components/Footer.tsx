"use client";

import { useAppConfig } from "@/context/AppConfigContext";
import { useClientBranding } from "@/context/ClientBrandingContext";

export default function Footer() {
  const branding = useClientBranding();
  const { config } = useAppConfig();
  return (
    <footer className="fixed bottom-0 left-0 right-0 bg-background/80 backdrop-blur-md border-t border-border/60 py-3 px-6 z-40">
      <div className="flex justify-between items-center text-xs text-muted-foreground max-w-7xl mx-auto">
        <span>{branding.company_name} · {branding.tagline}</span>
        <div className="flex items-center gap-4">
          <span>Voice workflows</span>
          <span className="text-border">|</span>
          {config?.uiVersion && <span>Version {config.uiVersion}</span>}
        </div>
      </div>
    </footer>
  );
}
