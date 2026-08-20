import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CareAgenda } from "./CareAgenda";
import { CareAgendaFilters } from "./CareAgendaFilters";

describe("CareAgenda", () => {
  it("keeps four visible sections and distinguishes empty sections", () => {
    const markup = renderToStaticMarkup(
      <CareAgenda
        loading={false}
        error=""
        data={{
          timezone: "Asia/Taipei",
          timezone_version: 1,
          local_today: "2026-08-16",
          buckets: {
            today_pending: [],
            overdue: [],
            today_resolved: [],
            next_seven_days: [],
          },
          totals: {
            today_pending: 0,
            overdue: 0,
            today_resolved: 0,
            next_seven_days: 0,
          },
          pages: {
            today_pending: { items: [], total_count: 0, next_cursor: null },
            overdue: { items: [], total_count: 0, next_cursor: null },
            today_resolved: { items: [], total_count: 0, next_cursor: null },
            next_seven_days: { items: [], total_count: 0, next_cursor: null },
          },
        }}
      />,
    );
    expect(markup).toContain("今天待處理");
    expect(markup).toContain("已逾期");
    expect(markup).toContain("今天已完成／略過／取消");
    expect(markup).toContain("未來七天");
  });

  it("shows the exact total and a load-more affordance when a bucket is paged", () => {
    const item = {
      occurrence_id: "occurrence-1",
      animal_id: "animal-1",
      animal_name: "小白",
      shelter_number: "A-001",
      reminder_type: "medication",
      title: "吃藥",
      instructions: "依管理員指示",
      scheduled_at: "2026-08-16T09:00:00+08:00",
      status: "pending" as const,
      version: 0,
      is_virtual: true,
      assignee_membership_id: null,
    };
    const markup = renderToStaticMarkup(
      <CareAgenda
        loading={false}
        error=""
        onLoadMore={() => undefined}
        data={{
          timezone: "Asia/Taipei",
          timezone_version: 1,
          local_today: "2026-08-16",
          buckets: {
            today_pending: [item],
            overdue: [],
            today_resolved: [],
            next_seven_days: [],
          },
          totals: {
            today_pending: 125,
            overdue: 0,
            today_resolved: 0,
            next_seven_days: 0,
          },
          pages: {
            today_pending: {
              items: [item],
              total_count: 125,
              next_cursor: "1",
            },
            overdue: { items: [], total_count: 0, next_cursor: null },
            today_resolved: { items: [], total_count: 0, next_cursor: null },
            next_seven_days: { items: [], total_count: 0, next_cursor: null },
          },
        }}
      />,
    );
    expect(markup).toContain("1 / 125");
    expect(markup).toContain("載入更多（尚有 124 筆）");
    expect(markup).toContain('class="reminder-card-grid"');
  });
});

describe("CareAgendaFilters", () => {
  it("uses the bottom-aligned filter layout", () => {
    const markup = renderToStaticMarkup(
      <CareAgendaFilters
        date="2026-08-19"
        reminderType=""
        status=""
        animalId=""
        assigneeMembershipId=""
        onDateChange={() => undefined}
        onReminderTypeChange={() => undefined}
        onStatusChange={() => undefined}
        onAnimalIdChange={() => undefined}
        onAssigneeChange={() => undefined}
        onToday={() => undefined}
      />,
    );

    expect(markup).toContain("care-agenda-filters");
    expect(markup).toContain("上一日");
    expect(markup).toContain("下一日");
  });
});
