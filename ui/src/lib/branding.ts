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
  favicon_url: "",
  support_email: "",
  primary_color: "#426b57",
  font: "geist",
};
