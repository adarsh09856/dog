export interface PlatformBranding {
  company_name: string;
  tagline: string;
  logo_url: string;
  favicon_url?: string;
  support_email?: string;
  primary_color: string;
  font: "geist" | "system";
}

export const DEFAULT_BRANDING: PlatformBranding = {
  company_name: "Kodewaves",
  tagline: "Voice agents for web and phone",
  logo_url: "",
  favicon_url: "/kodewaves-mark.svg",
  support_email: "",
  primary_color: "#426b57",
  font: "geist",
};

export const CLIENT_EDITION_DEFAULT_BRANDING: PlatformBranding = {
  ...DEFAULT_BRANDING,
  company_name: "Voice platform",
  tagline: "Voice agents for web and phone",
  favicon_url: "/voice-platform-mark.svg",
};

export function defaultBrandingForEdition(): PlatformBranding {
  return process.env.NEXT_PUBLIC_KODEWAVES_EDITION === "client"
    ? CLIENT_EDITION_DEFAULT_BRANDING
    : DEFAULT_BRANDING;
}
