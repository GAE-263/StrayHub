import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ObservationCategoryGroup } from "./ObservationCategoryGroup";
import { ObservationFilters } from "./ObservationFilters";
import type { Category, ObservationOption } from "./observationVocabulary";

const category: Category = {
  id: "emotion",
  code: "emotion",
  display_name: "情緒",
  description: "",
  status: "active",
  display_order: 0,
  source: "platform_default",
};

const option: ObservationOption = {
  id: "option-1",
  category_id: "emotion",
  organization_id: null,
  code: "emotion.calm",
  display_name: "平靜",
  description: "",
  status: "active",
  enabled: true,
  display_order: 0,
  requires_note: false,
  source: "platform_default",
  editable: false,
  has_historical_usage: false,
  historical_usage_count: 0,
  last_modified_at: "2026-08-11T00:00:00Z",
  last_modified_by: null,
  updated_at: "2026-08-11T00:00:00Z",
};

describe("observation vocabulary accessibility surfaces", () => {
  it("connects category controls to expandable content and uses text states", () => {
    const html = renderToStaticMarkup(
      React.createElement(ObservationCategoryGroup, {
        category,
        options: [],
        platformOptions: [option],
        canManage: false,
        onEdit: () => undefined,
        onLifecycle: () => undefined,
        onAudit: () => undefined,
        onMove: () => undefined,
      }),
    );

    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('aria-controls="category-content-emotion"');
    expect(html).toContain("啟用中");
    expect(html).toContain("自訂");
    expect(html).toContain("停用／封存");
  });

  it("provides labels for search and all combined filters", () => {
    const html = renderToStaticMarkup(
      React.createElement(ObservationFilters, {
        categories: [category],
        filters: { search: "", category: "all", status: "all", source: "all" },
        matchCount: 1,
        onChange: () => undefined,
      }),
    );

    expect(html).toContain("搜尋觀察詞彙");
    expect(html).toContain("觀察類別");
    expect(html).toContain("狀態");
    expect(html).toContain("來源");
    expect(html).toContain("清除搜尋與篩選");
  });
});
