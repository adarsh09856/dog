"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import SovereignBillingPage from "@/app/billing-sovereign/page";

export default function BillingRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/billing-sovereign");
  }, [router]);

  return <SovereignBillingPage />;
}
