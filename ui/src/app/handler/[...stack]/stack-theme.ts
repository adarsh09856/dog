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
    : "#426b57";
  const foreground = contrastForeground(primary);

  return {
    light: {
      background: "#f2f4ed",
      foreground: "#142b2c",
      card: "#fbfcf8",
      cardForeground: "#142b2c",
      popover: "#fbfcf8",
      popoverForeground: "#142b2c",
      primary,
      primaryForeground: foreground,
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
      ring: primary,
    },
    dark: {
      background: "#111e20",
      foreground: "#e7eee7",
      card: "#182827",
      cardForeground: "#e7eee7",
      popover: "#1c302d",
      popoverForeground: "#e7eee7",
      primary,
      primaryForeground: foreground,
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
      ring: primary,
    },
    radius: "0.625rem",
  };
}
