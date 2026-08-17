import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MedicalHistoryAuditPanel } from "./MedicalHistoryAuditPanel";
import { MedicalHistoryEntry } from "./MedicalHistoryEntry";
import { MedicalHistoryPanel } from "./MedicalHistoryPanel";

describe("MedicalHistoryPanel", () => {
  it("renders the short form, optional weight and manual-entry boundary", () => {
    const markup = renderToStaticMarkup(
      <MedicalHistoryPanel animalId="animal-1" />,
    );
    expect(markup).toContain("發生時間");
    expect(markup).toContain("體重（公斤，選填）");
    expect(markup).toContain("診所（選填）");
    expect(markup).toContain("獸醫（選填）");
    expect(markup).toContain("搜尋標題或內容");
    expect(markup).toContain("內容為管理員人工輸入");
    expect(markup).toContain("不會自動計算或調整藥量");
  });

  it("exposes filters, archive visibility and an honest loading state", () => {
    const markup = renderToStaticMarkup(
      <MedicalHistoryPanel animalId="animal-1" />,
    );
    expect(markup).toContain("篩選類型");
    expect(markup).toContain("顯示已封存");
    expect(markup).toContain("正在載入醫療歷史");
  });
});

describe("medical history supporting entries", () => {
  it("keeps same-day entry content visible and audit state explicit", () => {
    const entry = renderToStaticMarkup(
      <MedicalHistoryEntry title="回診" content="同日第二筆紀錄" />,
    );
    const audit = renderToStaticMarkup(
      <MedicalHistoryAuditPanel
        items={[
          {
            action: "medical_record.corrected",
            created_at: "2026-08-16T09:00:00Z",
          },
        ]}
      />,
    );
    expect(entry).toContain("同日第二筆紀錄");
    expect(audit).toContain("medical_record.corrected");
  });
});
