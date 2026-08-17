import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ReminderActionDialog } from "./ReminderActionDialog";

const item = {
  occurrence_id: "occurrence-1",
  animal_id: "animal-1",
  animal_name: "小白",
  shelter_number: "A-001",
  reminder_type: "medication",
  title: "每月預防藥",
  instructions: "依管理員輸入指示執行",
  scheduled_at: "2026-08-16T09:00:00+08:00",
  status: "pending" as const,
  version: 0,
  is_virtual: true,
  assignee_membership_id: null,
};

describe("ReminderActionDialog", () => {
  it("provides three-step action choices and optional completion time", () => {
    const markup = renderToStaticMarkup(
      <ReminderActionDialog
        item={item}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
    expect(markup).toContain("標記完成");
    expect(markup).toContain("略過");
    expect(markup).toContain("改期");
    expect(markup).toContain("取消本次");
    expect(markup).toContain("實際完成時間（選填）");
    expect(markup).toContain("確認處理");
  });
});
