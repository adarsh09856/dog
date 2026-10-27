"use client";

import { StackTheme } from "@stackframe/stack";
import type { ReactNode } from "react";

import { useClientBranding } from "@/context/ClientBrandingContext";

import { createStackAuthTheme } from "./stack-theme";

export function BrandAwareStackTheme({ children }: { children: ReactNode }) {
  const branding = useClientBranding();
  return (
    <StackTheme theme={createStackAuthTheme(branding.primary_color)}>
      {children}
    </StackTheme>
  );
}
