import { describe, expect, it } from "vitest";

import { DEFAULT_BRANDING } from "./branding";
import { brandingCssVariables } from "./brandingTheme";

describe("server and client branding theme variables", () => {
  it("uses the Kodewaves forest brand as the shared default", () => {
    expect(DEFAULT_BRANDING.primary_color).toBe("#426b57");
    expect(brandingCssVariables(DEFAULT_BRANDING, "light")["--primary"]).toBe(
      DEFAULT_BRANDING.primary_color,
    );
  });

  it("keeps accent text readable when the configured brand color is very light or dark", () => {
    const luminance = (hex: string) => {
      const channels = [1, 3, 5].map((index) => {
        const value = parseInt(hex.slice(index, index + 2), 16) / 255;
        return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
      });
      return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
    };
    for (const primary_color of ["#ffff00", "#111111"]) {
      for (const [theme, background] of [["light", "#f2f4ed"], ["dark", "#111e20"]] as const) {
        const text = brandingCssVariables({ ...DEFAULT_BRANDING, primary_color }, theme)["--cta-text"];
        expect(text).toMatch(/^#[0-9a-f]{6}$/i);
        const values = [luminance(text), luminance(background)].sort((a, b) => b - a);
        expect((values[0] + 0.05) / (values[1] + 0.05)).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("builds consistent light and dark palettes from the configured color", () => {
    const branding = { ...DEFAULT_BRANDING, primary_color: "#123456" };
    const light = brandingCssVariables(branding, "light");
    const dark = brandingCssVariables(branding, "dark");

    expect(light["--primary"]).toBe("#123456");
    expect(light["--brand-primary-color"]).toBe(light["--primary"]);
    expect(dark["--brand-primary-color"]).toBe(dark["--primary"]);
    expect(dark["--primary"]).not.toBe("#123456");
    expect(light["--cta"]).toBe(light["--primary"]);
    expect(dark["--sidebar-primary"]).toBe(dark["--primary"]);
    expect(light["--primary-foreground"]).toMatch(/^#[0-9a-f]{6}$/i);
    expect(dark["--primary-foreground"]).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it("includes the system font override only when configured", () => {
    expect(
      brandingCssVariables({ ...DEFAULT_BRANDING, font: "system" }, "dark")[
        "--brand-font-family"
      ],
    ).toContain("system-ui");
    expect(brandingCssVariables(DEFAULT_BRANDING, "dark")).not.toHaveProperty(
      "--brand-font-family",
    );
  });
});
