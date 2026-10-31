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

// Brand accents must remain legible on the light/dark surfaces even if the
// owner picks a near-white or near-black color. Preserve its hue while moving
// it only as far as needed to keep the shared UI readable.
function readableAccent(color: string, theme: BrandingTheme): string {
  const surface = theme === "light" ? "#f2f4ed" : "#111e20";
  const target = theme === "light" ? "#142b2c" : "#e7eee7";
  const surfaceLuminance = relativeLuminance(surface);
  const contrast = (candidate: string) => {
    const candidateLuminance = relativeLuminance(candidate);
    return (Math.max(candidateLuminance, surfaceLuminance) + 0.05)
      / (Math.min(candidateLuminance, surfaceLuminance) + 0.05);
  };
  if (contrast(color) >= 4.55) return color;
  let low = 0;
  let high = 1;
  for (let i = 0; i < 16; i++) {
    const middle = (low + high) / 2;
    if (contrast(mixHex(color, target, middle)) >= 4.55) low = middle;
    else high = middle;
  }
  return mixHex(color, target, low);
}

export function brandingCssVariables(
  branding: PlatformBranding,
  theme: BrandingTheme,
): BrandingCssVariables {
  const baseColor = /^#[0-9a-f]{6}$/i.test(branding.primary_color)
    ? branding.primary_color
    : "#426b57";
  const color = readableAccent(baseColor, theme);
  const accent = mixHex(color, theme === "dark" ? "#000000" : "#ffffff", theme === "dark" ? 0.3 : 0.14);
  const variables: BrandingCssVariables = {
    "--brand-primary-color": color,
    "--primary": color,
    "--sidebar-primary": color,
    "--cta": color,
    "--cta-text": readableAccent(color, theme),
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
