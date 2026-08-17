import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AnimalTimeline } from "./AnimalTimeline";
import { mapDays } from "./timelineMapping";
import { AnimalTodaySummary } from "../medical-care/AnimalTodaySummary";

describe("animal medical timeline presentation", () => {
  it("labels scheduled and actual events independently of has_report", () => {
    const markup = renderToStaticMarkup(
      <AnimalTimeline
        days={mapDays([
          {
            date: "2026-08-16",
            has_report: false,
            report_count: 0,
            events: [
              {
                id: "m1",
                kind: "medical_record",
                occurrence: "actual",
                title: "量體重",
                summary: "12 kg",
              },
            ],
            scheduled: [
              {
                id: "r1",
                title: "吃藥",
                status: "overdue",
                scheduled_at: "2026-08-16T01:00:00Z",
              },
            ],
          },
        ])}
      />,
    );
    expect(markup).toContain("已發生事件");
    expect(markup).toContain("預定照護");
    expect(markup).not.toContain("當日沒有事件");
  });

  it.each([
    [
      "今天沒有任何事件",
      { hasActivity: false, pendingCount: 0, overdueCount: 0 },
    ],
    [
      "今天有事件但沒有待辦",
      { hasActivity: true, pendingCount: 0, overdueCount: 0 },
    ],
    ["今天仍有待辦", { hasActivity: true, pendingCount: 1, overdueCount: 0 }],
    ["有逾期待辦", { hasActivity: true, pendingCount: 0, overdueCount: 1 }],
  ])("renders %s", (label, props) => {
    expect(
      renderToStaticMarkup(
        <AnimalTodaySummary localToday="2026-08-16" {...props} />,
      ),
    ).toContain(label);
  });

  it("renders a distinct error state", () => {
    expect(
      renderToStaticMarkup(
        <AnimalTodaySummary
          hasActivity={false}
          pendingCount={0}
          overdueCount={0}
          error="網路錯誤"
        />,
      ),
    ).toContain("網路錯誤");
  });
});
