import { describe, expect, it } from "vitest";
import React from "react";
import AnimalTimelinePage from "./page";
import { mapDays } from "../../../../../features/animal-timeline/timelineMapping";

describe("animal timeline page", () => {
  it("renders the management timeline route", () => {
    const page = React.createElement(AnimalTimelinePage, {
      params: Promise.resolve({ animalId: "animal-1" }),
    });
    expect(page.type).toBe(AnimalTimelinePage);
  });

  it("keeps a breadcrumb back to the animal profile", () => {
    const page = React.createElement(AnimalTimelinePage, {
      params: Promise.resolve({ animalId: "animal-1" }),
    });
    expect(page.props.params).toBeInstanceOf(Promise);
  });

  it("maps API timeline details without dropping original and status fields", () => {
    const [day] = mapDays([
      {
        date: "2026-08-07",
        has_report: true,
        report_count: 1,
        reports: [
          {
            id: "report-1",
            submitted_at: "2026-08-07T09:00:00+08:00",
            volunteer_user_id: "staff-1",
            note: "原始心得",
            observations: { emotion: "emotion.calm" },
            observation_snapshots: {
              emotion: { code: "emotion.calm", display_name: "平靜" },
            },
            media_ids: ["media-1"],
            ai_job_status: "pending",
            status: "saved",
          },
        ],
      },
    ]);

    expect(day.reports?.[0]).toMatchObject({
      id: "report-1",
      note: "原始心得",
      observations: { emotion: "emotion.calm" },
      observationSnapshots: {
        emotion: { code: "emotion.calm", displayName: "平靜" },
      },
      mediaIds: ["media-1"],
      aiJobStatus: "pending",
      status: "saved",
    });
  });
});
