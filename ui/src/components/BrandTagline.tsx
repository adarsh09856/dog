"use client";

import { useClientBranding } from "@/context/ClientBrandingContext";

export function BrandTagline({ className }: { className?: string }) {
  const { tagline } = useClientBranding();
  return <span className={className}>{tagline}</span>;
}
