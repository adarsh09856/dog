"use client";

import { ArrowRight } from "lucide-react";
import { useState } from "react";

import { useClientBranding } from "@/context/ClientBrandingContext";

import { EnterpriseModal } from "./EnterpriseModal";

interface PublicEnterpriseLeadCTAProps {
  label: string;
  className: string;
}

/** Use the hosted intake for SaaS and the installation-owned contact for client builds. */
export function PublicEnterpriseLeadCTA({ label, className }: PublicEnterpriseLeadCTAProps) {
  const [open, setOpen] = useState(false);
  const branding = useClientBranding();

  // Client installations own their public leads. The hosted onboarding API is
  // not part of the client image, so route enquiries to the configured
  // installation contact instead of showing a form that cannot be submitted.
  if (process.env.NEXT_PUBLIC_KODEWAVES_EDITION === "client") {
    const supportEmail = branding.support_email?.trim();
    if (supportEmail) {
      return (
        <a
          className={className}
          href={`mailto:${supportEmail}?subject=${encodeURIComponent("Installation enquiry")}`}
        >
          {label} <ArrowRight aria-hidden className="size-4" />
        </a>
      );
    }

    return (
      <p role="note" className="max-w-md text-sm leading-6 text-muted-foreground">
        Contact your installation administrator to discuss this installation.
      </p>
    );
  }

  return (
    <>
      <button type="button" className={className} onClick={() => setOpen(true)}>
        {label} <ArrowRight aria-hidden className="size-4" />
      </button>
      <EnterpriseModal open={open} onOpenChange={setOpen} source="landing_contact" />
    </>
  );
}
