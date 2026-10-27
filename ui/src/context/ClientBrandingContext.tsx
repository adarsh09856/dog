"use client";

import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useState,
} from "react";

import { DEFAULT_BRANDING, type PlatformBranding } from "@/lib/branding";
import { brandingCssVariables } from "@/lib/brandingTheme";
import { apiFetch } from "@/lib/kodewavesApi";

export type ClientBranding = PlatformBranding;

const ClientBrandingContext = createContext<ClientBranding>(DEFAULT_BRANDING);

export function notifyBrandingChanged() {
  window.dispatchEvent(new Event("kodewaves-branding-updated"));
  try {
    localStorage.setItem("kodewaves-branding-version", String(Date.now()));
  } catch {
    /* Same-tab refresh still works without browser storage. */
  }
}

export function ClientBrandingProvider({
  children,
  initialBranding = DEFAULT_BRANDING,
}: {
  children: ReactNode;
  initialBranding?: ClientBranding;
}) {
  const [branding, setBranding] = useState<ClientBranding>(initialBranding);
  const pathname = usePathname();
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    let active = true;
    let refreshRevision = 0;
    const refresh = () => {
      const revision = ++refreshRevision;
      apiFetch<ClientBranding>("/installation/branding")
        .then((value) => {
          if (active && revision === refreshRevision) {
            setBranding({ ...DEFAULT_BRANDING, ...value });
          }
        })
        .catch(() => {
          /* Keep the last usable brand during backend recovery. */
        });
    };
    const storageChanged = (event: StorageEvent) => {
      if (event.key === "kodewaves-branding-version") refresh();
    };
    refresh();
    window.addEventListener("kodewaves-branding-updated", refresh);
    window.addEventListener("focus", refresh);
    window.addEventListener("storage", storageChanged);
    const timer = window.setInterval(refresh, 60000);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener("kodewaves-branding-updated", refresh);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("storage", storageChanged);
    };
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    const section =
      pathname === "/"
        ? ""
        : pathname === "/pricing"
          ? "Plans and pricing"
          : pathname?.startsWith("/admin")
            ? "Admin"
            : pathname?.startsWith("/auth/signup")
              ? "Create account"
              : pathname?.startsWith("/auth/login")
                ? "Sign in"
                : "Workspace";
    document.title = section
      ? `${section} | ${branding.company_name}`
      : branding.company_name;
    let icon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (!icon) {
      icon = document.createElement("link");
      icon.rel = "icon";
      document.head.appendChild(icon);
    }
    icon.href = branding.favicon_url || "/favicon.ico";
    const variables = brandingCssVariables(
      branding,
      resolvedTheme === "light" ? "light" : "dark",
    );
    for (const [key, value] of Object.entries(variables)) {
      root.style.setProperty(key, value);
    }
    if (branding.font !== "system") root.style.removeProperty("--brand-font-family");
  }, [branding, pathname, resolvedTheme]);

  return (
    <ClientBrandingContext.Provider value={branding}>
      {children}
    </ClientBrandingContext.Provider>
  );
}

export function useClientBranding(): ClientBranding {
  return useContext(ClientBrandingContext);
}
