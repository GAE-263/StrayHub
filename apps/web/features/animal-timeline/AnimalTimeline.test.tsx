import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AnimalTimeline } from "./AnimalTimeline";

describe("AnimalTimeline", () => {
  it("exposes no-report days and report expansion state", () => {
    const element = React.createElement(AnimalTimeline, {
      days: [
        { date: "2026-08-08", hasReport: false, reportCount: 0 },
        {
          date: "2026-08-07",
          hasReport: true,
          reportCount: 1,
          reports: [{ id: "report-1", note: "原始心得", aiJobStatus: "pending" }],
        },
      ],
    });
    const markup = renderToStaticMarkup(element);
    expect(markup).toContain("當日無回報");
    expect(markup).toContain("有回報");
  });

  it("has explicit loading and error branches", () => {
    expect(
      renderToStaticMarkup(React.createElement(AnimalTimeline, { days: [], loading: true })),
    ).toContain("正在載入");
    expect(
      renderToStaticMarkup(React.createElement(AnimalTimeline, { days: [], error: "403" })),
    ).toContain("歷程載入失敗");
  });
});
