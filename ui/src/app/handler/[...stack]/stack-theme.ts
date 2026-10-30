// Stack's theme parser accepts hex colors, so resolve the shared brand color
// here instead of relying on CSS tokens Stack does not inherit in every route.

import type { StackTheme } from "@stackframe/stack";
import type { ComponentProps } from "react";

import { DEFAULT_BRANDING } from "@/lib/branding";
import { brandingCssVariables } from "@/lib/brandingTheme";

type ThemeConfig = NonNullable<ComponentProps<typeof StackTheme>["theme"]>;

export function createStackAuthTheme(primaryColor: string): ThemeConfig {
  const branding = {
    ...DEFAULT_BRANDING,
    primary_color: /^#[0-9a-f]{6}$/i.test(primaryColor)
      ? primaryColor
      : DEFAULT_BRANDING.primary_color,
  };
  const lightTokens = brandingCssVariables(branding, "light");
  const darkTokens = brandingCssVariables(branding, "dark");
  const lightPrimary = lightTokens["--brand-primary-color"];
  const darkPrimary = darkTokens["--brand-primary-color"];

  return {
    light: {
      background: "#f2f4ed",
      foreground: "#142b2c",
      card: "#fbfcf8",
      cardForeground: "#142b2c",
      popover: "#fbfcf8",
      popoverForeground: "#142b2c",
      primary: lightPrimary,
      primaryForeground: lightTokens["--primary-foreground"],
      secondary: "#e2e8de",
      secondaryForeground: "#28483b",
      muted: "#e8ece3",
      mutedForeground: "#58685f",
      accent: "#ece4d2",
      accentForeground: "#293931",
      destructive: "#dc2626",
      destructiveForeground: "#ffffff",
      border: "#d6ded3",
      input: "#c8d4ca",
      ring: lightPrimary,
    },
    dark: {
      background: "#111e20",
      foreground: "#e7eee7",
      card: "#182827",
      cardForeground: "#e7eee7",
      popover: "#1c302d",
      popoverForeground: "#e7eee7",
      primary: darkPrimary,
      primaryForeground: darkTokens["--primary-foreground"],
      secondary: "#263b35",
      secondaryForeground: "#e7eee7",
      muted: "#203430",
      mutedForeground: "#aec1b5",
      accent: "#424234",
      accentForeground: "#e7eee7",
      destructive: "#ef4444",
      destructiveForeground: "#e7eee7",
      border: "#304344",
      input: "#49615a",
      ring: darkPrimary,
    },
    radius: "0.625rem",
  };
}
