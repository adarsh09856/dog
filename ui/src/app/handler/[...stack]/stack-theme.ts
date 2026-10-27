// Stack's theme parser accepts hex colors, so resolve the shared brand color
// here instead of relying on CSS tokens Stack does not inherit in every route.

import type { StackTheme } from "@stackframe/stack";
import type { ComponentProps } from "react";

type ThemeConfig = NonNullable<ComponentProps<typeof StackTheme>["theme"]>;

function contrastForeground(hex: string): string {
  const channels = [1, 3, 5].map((index) => {
    const channel = parseInt(hex.slice(index, index + 2), 16) / 255;
    return channel <= 0.04045
      ? channel / 12.92
      : ((channel + 0.055) / 1.055) ** 2.4;
  });
  const luminance =
    channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  const darkContrast = (luminance + 0.05) / (0.006 + 0.05);
  const lightContrast = 1.05 / (luminance + 0.05);
  return darkContrast >= lightContrast ? "#07111b" : "#ffffff";
}

export function createStackAuthTheme(primaryColor: string): ThemeConfig {
  const primary = /^#[0-9a-f]{6}$/i.test(primaryColor)
    ? primaryColor
    : "#2563eb";
  const foreground = contrastForeground(primary);

  return {
    light: {
      background: "#ffffff",
      foreground: "#18181b",
      card: "#ffffff",
      cardForeground: "#18181b",
      popover: "#ffffff",
      popoverForeground: "#18181b",
      primary,
      primaryForeground: foreground,
      secondary: "#f4f4f5",
      secondaryForeground: "#18181b",
      muted: "#f4f4f5",
      mutedForeground: "#71717a",
      accent: "#f4f4f5",
      accentForeground: "#18181b",
      destructive: "#dc2626",
      destructiveForeground: "#ffffff",
      border: "#e4e4e7",
      input: "#e4e4e7",
      ring: primary,
    },
    dark: {
      background: "#27272a",
      foreground: "#fafafa",
      card: "#27272a",
      cardForeground: "#fafafa",
      popover: "#27272a",
      popoverForeground: "#fafafa",
      primary,
      primaryForeground: foreground,
      secondary: "#3f3f46",
      secondaryForeground: "#fafafa",
      muted: "#3f3f46",
      mutedForeground: "#a1a1aa",
      accent: "#3f3f46",
      accentForeground: "#fafafa",
      destructive: "#ef4444",
      destructiveForeground: "#fafafa",
      border: "#3f3f46",
      input: "#3f3f46",
      ring: primary,
    },
    radius: "0.625rem",
  };
}
