import { describe, expect, it } from "vitest";

import {
  canonicalVolunteerLiffStatusQuery,
  clearVolunteerLiffStatusIntent,
  persistVolunteerLiffStatusIntent,
  resolveVolunteerLiffLifecycleIntent,
} from "./volunteerLiffIntentLifecycle";

const organizationId = "11111111-1111-4111-8111-111111111111";

function storage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => void values.delete(key),
    setItem: (key, value) => void values.set(key, value),
  };
}

describe("volunteer LIFF intent lifecycle", () => {
  it("restores status across a secondary redirect that loses query state", () => {
    const session = storage();
    const initial = resolveVolunteerLiffLifecycleIntent(
      `liff.state=${encodeURIComponent("?view=status")}`,
      session,
      100,
    );
    persistVolunteerLiffStatusIntent(initial, session, 100);

    expect(resolveVolunteerLiffLifecycleIntent("", session, 200).view).toBe(
      "status",
    );
  });

  it("does not override an explicit application intent or retain expired state", () => {
    const session = storage();
    persistVolunteerLiffStatusIntent(
      { view: "status", targetConflict: false },
      session,
      100,
    );
    expect(
      resolveVolunteerLiffLifecycleIntent("view=application", session, 200)
        .view,
    ).toBe("application");
    expect(resolveVolunteerLiffLifecycleIntent("", session, 201).view).toBe(
      "application",
    );

    persistVolunteerLiffStatusIntent(
      { view: "status", targetConflict: false },
      session,
      300,
    );
    expect(
      resolveVolunteerLiffLifecycleIntent(
        `organization_id=${organizationId}`,
        session,
        400,
      ).view,
    ).toBe("application");
    expect(resolveVolunteerLiffLifecycleIntent("", session, 401).view).toBe(
      "application",
    );

    persistVolunteerLiffStatusIntent(
      { view: "status", targetConflict: false },
      session,
      500,
    );
    expect(resolveVolunteerLiffLifecycleIntent("", session, 300_501).view).toBe(
      "application",
    );
  });

  it("canonicalizes only validated status fields", () => {
    expect(
      canonicalVolunteerLiffStatusQuery({
        view: "status",
        organizationId,
        targetConflict: false,
      }),
    ).toBe(`view=status&organization_id=${organizationId}`);
    expect(
      canonicalVolunteerLiffStatusQuery({
        view: "status",
        organizationId: "unsafe",
        shelterEntryReference: "do-not-copy-entry-token",
        targetConflict: false,
      }),
    ).toBe("view=status");
  });

  it("clears the handoff after canonicalization or explicit navigation", () => {
    const session = storage();
    persistVolunteerLiffStatusIntent(
      { view: "status", targetConflict: false },
      session,
      100,
    );
    clearVolunteerLiffStatusIntent(session);
    expect(resolveVolunteerLiffLifecycleIntent("", session, 200).view).toBe(
      "application",
    );
  });
});
