import { describe, expect, it } from "vitest";

import { createStackAuthTheme } from "./stack-theme";

describe("Stack auth brand theme", () => {
  it("uses the configured brand color in light and dark auth flows", () => {
    const theme = createStackAuthTheme("#123456");
    expect(theme.light?.primary).toBe("#123456");
    expect(theme.dark?.primary).toBe("#71859a");
    expect(theme.light?.ring).toBe("#123456");
    expect(theme.dark?.ring).toBe("#71859a");
  });

  it("keeps readable primary button text and rejects invalid brand colors", () => {
    const lightBrand = createStackAuthTheme("#ffffff");
    const darkBrand = createStackAuthTheme("#000000");
    const invalidBrand = createStackAuthTheme("amber");
    expect(lightBrand.light?.primaryForeground).toBe("#07111b");
    expect(darkBrand.dark?.primary).toBe("#666666");
    expect(darkBrand.dark?.primaryForeground).toBe("#ffffff");
    expect(invalidBrand.light?.primary).toBe("#426b57");
    expect(invalidBrand.light?.background).toBe("#f2f4ed");
    expect(invalidBrand.dark?.background).toBe("#111e20");
  });
});
