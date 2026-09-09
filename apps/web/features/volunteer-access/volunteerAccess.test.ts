import { describe, expect, it } from "vitest";

import { safeVolunteerError } from "./volunteerAccess";

describe("safeVolunteerError", () => {
  it("distinguishes LINE provider outages from persistence failures", () => {
    expect(safeVolunteerError("line_identity_provider_unavailable")).toBe(
      "LINE 身分服務暫時無法使用，請稍後再試。",
    );
    expect(safeVolunteerError("internal_error")).toBe(
      "系統暫時無法完成申請，請稍後再試。",
    );
    expect(safeVolunteerError("dependency_unavailable")).toBe(
      "系統暫時無法完成申請，請稍後再試。",
    );
  });
});
