import { describe, expect, it } from "vitest";

import { DEFAULT_BRANDING } from "./branding";
import { brandingCssVariables } from "./brandingTheme";

describe("server and client branding theme variables", () => {
  it("builds consistent light and dark palettes from the configured color", () => {
    const branding = { ...DEFAULT_BRANDING, primary_color: "#123456" };
    const light = brandingCssVariables(branding, "light");
    const dark = brandingCssVariables(branding, "dark");

    expect(light["--primary"]).toBe("#123456");
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
