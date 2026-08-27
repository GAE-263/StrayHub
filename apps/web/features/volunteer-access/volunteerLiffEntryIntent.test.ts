import { describe, expect, it } from "vitest";

import { parseVolunteerLiffEntryIntent } from "./volunteerLiffEntryIntent";

const organizationA = "11111111-1111-4111-8111-111111111111";
const organizationB = "22222222-2222-4222-8222-222222222222";

describe("parseVolunteerLiffEntryIntent", () => {
  it("defaults to the application flow", () => {
    expect(parseVolunteerLiffEntryIntent("")).toEqual({
      view: "application",
      targetConflict: false,
    });
  });

  it("reads direct and encoded status intents", () => {
    expect(parseVolunteerLiffEntryIntent("view=status").view).toBe("status");
    expect(
      parseVolunteerLiffEntryIntent(
        `liff.state=${encodeURIComponent("?view=status")}`,
      ).view,
    ).toBe("status");
  });

  it("prefers an explicit direct display intent", () => {
    const result = parseVolunteerLiffEntryIntent(
      `view=application&liff.state=${encodeURIComponent("?view=status")}`,
    );
    expect(result.view).toBe("application");
  });

  it("preserves organization and entry-reference targets", () => {
    expect(
      parseVolunteerLiffEntryIntent(`organization_id=${organizationA}`),
    ).toMatchObject({ organizationId: organizationA });
    expect(
      parseVolunteerLiffEntryIntent(
        `liff.state=${encodeURIComponent("?shelter_entry_reference=opaque-entry")}`,
      ),
    ).toMatchObject({ shelterEntryReference: "opaque-entry" });
  });

  it("drops conflicting target selectors for safe recovery", () => {
    const result = parseVolunteerLiffEntryIntent(
      `organization_id=${organizationA}&liff.state=${encodeURIComponent(`?organization_id=${organizationB}`)}`,
    );
    expect(result).toMatchObject({ targetConflict: true });
    expect(result.organizationId).toBeUndefined();
    expect(result.shelterEntryReference).toBeUndefined();
    expect(
      parseVolunteerLiffEntryIntent(
        `organization_id=${organizationA}&shelter_entry_reference=opaque-entry`,
      ).targetConflict,
    ).toBe(true);
  });

  it("ignores malformed and full-URL LIFF state", () => {
    expect(
      parseVolunteerLiffEntryIntent(
        `liff.state=${encodeURIComponent("https://evil.example/?view=status")}`,
      ).view,
    ).toBe("application");
    expect(
      parseVolunteerLiffEntryIntent(`liff.state=${"x".repeat(2049)}`).view,
    ).toBe("application");
  });
});
