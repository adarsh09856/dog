"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AutomationRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/workflow");
  }, [router]);

  return null;
}
