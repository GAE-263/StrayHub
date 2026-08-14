import { describe, expect, it } from "vitest";
import { LOGIN_STATE_COPY, MANAGEMENT_HOME_STATE_COPY } from "./route-state";

describe("route state contracts", () => {
  it("defines every login state with a Traditional Chinese next step", () => {
    expect(Object.keys(LOGIN_STATE_COPY)).toEqual([
      "idle",
      "saving",
      "success",
      "invalidCredentials",
      "noShelterAccess",
      "contextFailure",
    ]);
    for (const state of Object.values(LOGIN_STATE_COPY))
      expect(state.nextStep).toMatch(/[\u4e00-\u9fff]/);
  });

  it("defines management home permission, error and empty next steps", () => {
    expect(MANAGEMENT_HOME_STATE_COPY.permissionDenied.nextStep).toContain(
      "授權收容所",
    );
    expect(MANAGEMENT_HOME_STATE_COPY.error.nextStep).toContain("重試");
    expect(MANAGEMENT_HOME_STATE_COPY.emptyRecentReports.nextStep).toContain(
      "動物清單",
    );
  });
});
