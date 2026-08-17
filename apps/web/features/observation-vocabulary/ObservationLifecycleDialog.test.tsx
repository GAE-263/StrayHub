import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ObservationLifecycleDialog } from "./ObservationLifecycleDialog";
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
  has_historical_usage: true,
  historical_usage_count: 2,
  last_modified_at: "2026-08-11T00:00:00Z",
  last_modified_by: null,
  updated_at: "2026-08-11T00:00:00Z",
};

describe("ObservationLifecycleDialog", () => {
  it("explains the non-destructive impact before disabling", () => {
    const html = renderToStaticMarkup(
      React.createElement(ObservationLifecycleDialog, {
        option: sample,
        action: "disable",
        onConfirm: async () => undefined,
        onCancel: () => undefined,
      }),
    );

    expect(html).toContain("確認停用");
    expect(html).toContain("不會出現在新的回報表單");
    expect(html).toContain("歷史回報仍會保留");
    expect(html).toContain("取消");
    expect(html).toContain('role="alertdialog"');
  });

  it("uses a recovery message for restore", () => {
    const html = renderToStaticMarkup(
      React.createElement(ObservationLifecycleDialog, {
        option: { ...sample, status: "disabled", enabled: false },
        action: "restore",
        onConfirm: async () => undefined,
        onCancel: () => undefined,
      }),
    );

    expect(html).toContain("確認恢復");
    expect(html).toContain("重新出現在新的回報表單");
  });
});
