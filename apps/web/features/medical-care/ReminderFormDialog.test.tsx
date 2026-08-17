import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ReminderFormDialog } from "./ReminderFormDialog";

describe("ReminderFormDialog", () => {
  it("renders recurrence controls and medication safety boundary", () => {
    const markup = renderToStaticMarkup(
      <ReminderFormDialog open animalId="animal-1" onClose={() => {}} />,
    );
    expect(markup).toContain("重複週期");
    expect(markup).toContain("每月");
    expect(markup).toContain("系統不會依體重計算藥量");
    expect(markup).not.toContain("提前提醒");
  });
});
