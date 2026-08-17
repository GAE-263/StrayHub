import { describe, expect, it } from "vitest";
import { reportAIStatusSummary } from "../../report-detail-state";

describe("report detail state mapping", () => {
  it("maps processing, failed and succeeded AI observations to user states", () => {
    const summary = reportAIStatusSummary([
      {
        id: "processing",
        status: "running",
      },
      {
        id: "failed",
        status: "failed",
      },
      {
        id: "review",
        status: "succeeded",
      },
    ]);

    expect(summary.map((item) => item.kind)).toEqual([
      "processing",
      "ai-failed",
      "needs-review",
    ]);
    expect(summary.map((item) => item.label)).toEqual([
      "AI 處理中",
      "AI 處理失敗",
      "需要人工覆核",
    ]);
  });
});
