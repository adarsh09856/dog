"use client";

import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

import { defaultBrandingForEdition, type PlatformBranding } from "@/lib/branding";
import { brandingCssVariables } from "@/lib/brandingTheme";
import { apiFetch } from "@/lib/kodewavesApi";

export type ClientBranding = PlatformBranding;

const ClientBrandingContext = createContext<ClientBranding>(defaultBrandingForEdition());

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
  initialBranding = defaultBrandingForEdition(),
}: {
  children: ReactNode;
  initialBranding?: ClientBranding;
}) {
  const [branding, setBranding] = useState<ClientBranding>(initialBranding);
  const pathname = usePathname();
  const { resolvedTheme } = useTheme();
  const lastBrandingTagline = useRef(branding.tagline);

  useEffect(() => {
    let active = true;
    let refreshRevision = 0;
    const refresh = () => {
      const revision = ++refreshRevision;
      apiFetch<ClientBranding>("/installation/branding")
        .then((value) => {
          if (active && revision === refreshRevision) {
            setBranding({ ...defaultBrandingForEdition(), ...value });
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
    const previousTagline = lastBrandingTagline.current;
    const section =
      pathname === "/"
        ? ""
        : pathname === "/pricing"
          ? "Plans and pricing"
          : pathname === "/platform" || pathname?.startsWith("/platform/")
            ? "Platform"
            : pathname === "/deployment" || pathname?.startsWith("/deployment/")
              ? "Deployment"
              : pathname?.startsWith("/superadmin")
                ? "Superadmin"
                : pathname?.startsWith("/admin")
                  ? "Admin"
                  : pathname?.startsWith("/auth/signup")
                    ? "Create account"
                    : pathname?.startsWith("/auth/login")
                      ? "Sign in"
                      : "Workspace";
    const expectedTitle = section
      ? `${section} | ${branding.company_name}`
      : branding.company_name;
    const syncMetadata = () => {
      // Next can apply server metadata after the client branding refresh.
      if (document.title !== expectedTitle) document.title = expectedTitle;
      let description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
      if (!description) {
        description = document.createElement("meta");
        description.name = "description";
        document.head.appendChild(description);
      }
      // The root layout uses the platform tagline as its default description.
      // Keep that default in sync when branding changes, while preserving
      // page-specific metadata supplied by Next for public routes.
      if (
        !description.content ||
        description.content === previousTagline ||
        description.content === branding.tagline
      ) {
        description.content = branding.tagline;
      }
    };
    syncMetadata();
    const metadataObserver = new MutationObserver(syncMetadata);
    metadataObserver.observe(document.head, {
      childList: true,
      characterData: true,
      subtree: true,
    });
    let icon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (!icon) {
      icon = document.createElement("link");
      icon.rel = "icon";
      document.head.appendChild(icon);
    }
    const fallback = defaultBrandingForEdition();
    icon.href = branding.favicon_url || fallback.favicon_url || "";
    const variables = brandingCssVariables(
      branding,
      resolvedTheme === "light" ? "light" : "dark",
    );
    lastBrandingTagline.current = branding.tagline;
    for (const [key, value] of Object.entries(variables)) {
      root.style.setProperty(key, value);
    }
    if (branding.font !== "system") root.style.removeProperty("--brand-font-family");
    return () => metadataObserver.disconnect();
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
