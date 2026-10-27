import type { PlatformBranding } from "@/lib/branding";

export type BrandingTheme = "light" | "dark";
export type BrandingCssVariables = Record<`--${string}`, string>;

function relativeLuminance(hex: string): number {
  const rgb = [1, 3, 5].map((index) => {
    const channel = parseInt(hex.slice(index, index + 2), 16) / 255;
    return channel <= 0.04045
      ? channel / 12.92
      : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}

function foregroundFor(hex: string): string {
  const backgroundLuminance = relativeLuminance(hex);
  const darkForeground = "#07111b";
  const darkLuminance = relativeLuminance(darkForeground);
  const darkContrast = (backgroundLuminance + 0.05) / (darkLuminance + 0.05);
  const lightContrast = 1.05 / (backgroundLuminance + 0.05);
  return darkContrast >= lightContrast ? darkForeground : "#ffffff";
}

function mixHex(foreground: string, background: string, foregroundWeight: number): string {
  const channels = [1, 3, 5].map((index) => {
    const front = parseInt(foreground.slice(index, index + 2), 16);
    const back = parseInt(background.slice(index, index + 2), 16);
    return Math.round(front * foregroundWeight + back * (1 - foregroundWeight))
      .toString(16)
      .padStart(2, "0");
  });
  return `#${channels.join("")}`;
}

export function brandingCssVariables(
  branding: PlatformBranding,
  theme: BrandingTheme,
): BrandingCssVariables {
  const baseColor = /^#[0-9a-f]{6}$/i.test(branding.primary_color)
    ? branding.primary_color
    : "#304c73";
  const color =
    theme === "dark" && foregroundFor(baseColor) === "#ffffff"
      ? mixHex(baseColor, "#ffffff", 0.6)
      : baseColor;
  const accent = mixHex(color, theme === "dark" ? "#000000" : "#ffffff", theme === "dark" ? 0.3 : 0.14);
  const variables: BrandingCssVariables = {
    "--primary": color,
    "--sidebar-primary": color,
    "--cta": color,
    "--ring": color,
    "--accent": accent,
    "--sidebar-accent": accent,
    "--primary-foreground": foregroundFor(color),
    "--sidebar-primary-foreground": foregroundFor(color),
    "--cta-foreground": foregroundFor(color),
    "--accent-foreground": foregroundFor(accent),
    "--sidebar-accent-foreground": foregroundFor(accent),
  };
  if (branding.font === "system") {
    variables["--brand-font-family"] =
      "system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  }
  return variables;
}
