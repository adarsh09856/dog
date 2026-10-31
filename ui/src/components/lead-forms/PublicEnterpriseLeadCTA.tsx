"use client";

import { ArrowRight } from "lucide-react";
import { useState } from "react";

import { EnterpriseModal } from "./EnterpriseModal";

interface PublicEnterpriseLeadCTAProps {
  label: string;
  className: string;
}

/** Public route into the same persisted enterprise intake used by the workspace. */
export function PublicEnterpriseLeadCTA({ label, className }: PublicEnterpriseLeadCTAProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button type="button" className={className} onClick={() => setOpen(true)}>
        {label} <ArrowRight aria-hidden className="size-4" />
      </button>
      <EnterpriseModal open={open} onOpenChange={setOpen} source="landing_contact" />
    </>
  );
}
