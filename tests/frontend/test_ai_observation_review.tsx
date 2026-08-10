import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AIObservationPanel } from "../../apps/web/features/ai-observation/AIObservationPanel";

describe("AIObservationPanel", () => {
  it("separates AI, original source and human review regions", () => {
    const html = renderToStaticMarkup(
      React.createElement(AIObservationPanel, {
        observation: {
          id: "obs-1",
          status: "succeeded",
          sourceType: "photo",
          sourceId: "media-1",
          rawAiOutput: { observations: [{ code: "appearance.changed" }] },
          validatedAiObservation: {
            observations: [{ code: "appearance.changed" }],
          },
          humanReviewResult: null,
        },
      }),
    );
    expect(html).toContain("AI 輔助擷取");
    expect(html).toContain("原始資料");
    expect(html).toContain("AI 擷取結果");
    expect(html).toContain("來源：清理後照片");
    expect(html).toContain("確認");
    expect(html).toContain("拒絕");
    expect(html).toContain("修正");
  });

  it("does not describe failed processing as normal", () => {
    const html = renderToStaticMarkup(
      React.createElement(AIObservationPanel, {
        observation: {
          id: "obs-2",
          status: "failed",
          sourceType: "note",
          sourceId: "report-2",
          rawAiOutput: null,
          validatedAiObservation: null,
          humanReviewResult: null,
        },
      }),
    );
    expect(html).toContain("AI 處理失敗");
    expect(html).not.toContain("正常");
  });
});
