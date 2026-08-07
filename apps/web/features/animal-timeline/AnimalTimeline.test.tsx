import { describe, expect, it } from "vitest";

import { AnimalTimeline } from "./AnimalTimeline";

describe("AnimalTimeline", () => {
  it("renders an explicit no-report state", () => {
    const element = AnimalTimeline({
      days: [{ date: "2026-08-07", hasReport: false, reportCount: 0 }],
    });
    const list = element.props.children as Array<{
      props: { children: unknown };
    }>;
    const day = list[0].props.children as Array<{
      props: { children: unknown };
    }>;

    expect(day[1].props.children).toContain("當日無回報");
  });

  it("keeps every report on a day and separates AI status from raw content", () => {
    const element = AnimalTimeline({
      days: [
        {
          date: "2026-08-07",
          hasReport: true,
          reportCount: 2,
          reports: [
            {
              id: "report-a",
              note: "原始心得",
              observations: { feeding: "feeding.normal" },
              aiJobStatus: "failed",
              status: "saved",
            },
            { id: "report-b", note: null, aiJobStatus: "pending" },
          ],
        },
      ],
    });
    const day = element.props.children[0].props.children as Array<{
      props: { children: unknown };
    }>;
    const reports = (day.slice(2) as unknown[]).flat() as Array<{
      props: { children: unknown };
    }>;
    const reportChildren = reports[0].props.children as Array<{
      props: { children: unknown };
    }>;

    expect(reports).toHaveLength(2);
    expect(reportChildren[1].props.children).toContain("原始心得");
    expect(reportChildren[4].props.children).toContain("failed");
  });
});
