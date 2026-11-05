import "server-only";

import { cache } from "react";

import { getServerBackendUrl } from "@/lib/apiClient";
import { defaultBrandingForEdition, type PlatformBranding } from "@/lib/branding";

export const getServerBranding = cache(async (): Promise<PlatformBranding> => {
  const fallback = defaultBrandingForEdition();
  try {
    const response = await fetch(
      `${getServerBackendUrl()}/api/v1/installation/branding`,
      {
        cache: "no-store",
        signal: AbortSignal.timeout(3000),
      },
    );
    if (response.ok) return { ...fallback, ...(await response.json()) };
  } catch {
    /* Render a usable page while the backend recovers. */
  }
  return fallback;
});
