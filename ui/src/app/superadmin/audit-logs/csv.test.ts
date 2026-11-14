import { describe, expect, it } from "vitest";

import { buildAuditLogsCsv } from "./csv";

describe("buildAuditLogsCsv", () => {
  it("escapes CSV fields and neutralizes spreadsheet formulas", () => {
    const csv = buildAuditLogsCsv([{
      id: 1,
      action: '=HYPERLINK("https://bad.example")',
      target_resource: 'user, "7"',
      details: { note: "safe" },
      created_at: "not-a-date",
    }]);

    expect(csv).toContain('"\'=HYPERLINK(""https://bad.example"")"');
    expect(csv).toContain('"user, ""7"""');
    expect(csv).toContain('"{""note"":""safe""}"');
  });

  it("returns the CSV header for an empty audit log", () => {
    expect(buildAuditLogsCsv([])).toBe(
      '"Timestamp","Admin / Actor","Action","Target Resource","Payload Details","IP Address"',
    );
  });
});
