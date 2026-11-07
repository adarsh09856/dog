import { describe, expect, it } from "vitest";

import { DEFAULT_BRANDING } from "./branding";
import { brandingCssVariables } from "./brandingTheme";

describe("server and client branding theme variables", () => {
  it("uses the Kodewaves forest brand as the shared default", () => {
    expect(DEFAULT_BRANDING.primary_color).toBe("#426b57");
    expect(DEFAULT_BRANDING.favicon_url).toBe("/kodewaves-mark.svg");
    expect(brandingCssVariables(DEFAULT_BRANDING, "light")["--brand-primary-color"]).toBe(
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

  it("applies the configured brand color to shared controls in both themes", () => {
    const branding = { ...DEFAULT_BRANDING, primary_color: "#123456" };
    const light = brandingCssVariables(branding, "light");
    const dark = brandingCssVariables(branding, "dark");

    expect(light["--brand-primary-color"]).toBe("#123456");
    expect(dark["--brand-primary-color"]).not.toBe("#123456");
    expect(light["--primary"]).toBe("#123456");
    expect(dark["--primary"]).toBe(dark["--brand-primary-color"]);
    expect(light["--primary-foreground"]).toBe("#ffffff");
    expect(dark["--primary-foreground"]).toMatch(/^#[0-9a-f]{6}$/i);
    expect(light["--sidebar-ring"]).toBe("#123456");
    expect(light["--cta"]).toBe("#123456");
    expect(dark["--sidebar-primary"]).toBe(dark["--brand-primary-color"]);
    // Keep the restrained neutral surfaces neutral; branding changes control
    // emphasis, not every pale accent background on the product.
    expect(light).not.toHaveProperty("--accent");
    expect(dark).not.toHaveProperty("--accent");
    expect(light["--cta-foreground"]).toMatch(/^#[0-9a-f]{6}$/i);
    expect(dark["--cta-foreground"]).toMatch(/^#[0-9a-f]{6}$/i);
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
