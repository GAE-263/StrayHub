import { describe, expect, it } from "vitest";
import { getStatusSemantics, STATUS_LABELS } from "./ui-status";

describe("UI status semantics", () => {
  it("keeps saving separate from loading", () => {
    expect(STATUS_LABELS.saving).toBe("儲存中");
    expect(getStatusSemantics("saving").ariaLive).toBe("polite");
    expect(getStatusSemantics("loading").label).toBe("載入中");
  });

  it("uses assertive announcements only for blocking errors", () => {
    expect(getStatusSemantics("error").ariaLive).toBe("assertive");
    expect(getStatusSemantics("ai-failed").ariaLive).toBe("polite");
  });
});
