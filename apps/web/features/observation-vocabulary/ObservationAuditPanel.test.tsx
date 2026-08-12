import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ObservationAuditPanel } from "./ObservationAuditPanel";
import type { ObservationOption } from "./observationVocabulary";

const sample: ObservationOption = {
  id: "option-1",
  category_id: "emotion",
  organization_id: "org-a",
  code: "emotion.shelter_calm",
  display_name: "收容所自訂平靜",
  description: "",
  status: "active",
  enabled: true,
  display_order: 0,
  requires_note: false,
  source: "organization_extension",
  editable: true,
  has_historical_usage: false,
  historical_usage_count: 0,
  last_modified_at: "2026-08-11T00:00:00Z",
  last_modified_by: null,
  updated_at: "2026-08-11T00:00:00Z",
};

describe("ObservationAuditPanel", () => {
  it("exposes a read-only audit surface for the current option", () => {
    const html = renderToStaticMarkup(
      React.createElement(ObservationAuditPanel, {
        option: sample,
        onClose: () => undefined,
      }),
    );

    expect(html).toContain("變更紀錄：收容所自訂平靜");
    expect(html).toContain("只顯示目前收容所此自訂選項的唯讀紀錄");
    expect(html).toContain("正在載入變更紀錄");
  });
});
