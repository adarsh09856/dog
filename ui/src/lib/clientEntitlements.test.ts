import { describe, expect, it } from "vitest";

import { requiredFeatureForUiPath } from "./clientEntitlements";

describe("requiredFeatureForUiPath", () => {
  it.each([
    ["/workflow", "voice"],
    ["/workflow/21/runs", "voice"],
    ["/overview", "voice"],
    ["/api-keys", "voice"],
    ["/campaigns", "campaigns"],
    ["/telephony-configurations", "telephony"],
    ["/crm/contacts", "crm"],
    ["/appointments", "appointments"],
    ["/forms", "forms"],
    ["/widgets", "widgets"],
    ["/files", "knowledge_base"],
    ["/billing-sovereign", "billing"],
  ])("maps %s to the %s grant", (path, feature) => {
    expect(requiredFeatureForUiPath(path)).toBe(feature);
  });

  it.each(["/settings", "/campaigns-archive"])(
    "leaves general path %s available to the licensed account shell",
    (path) => expect(requiredFeatureForUiPath(path)).toBeNull(),
  );
});
