import { describe, expect, it } from "vitest";
import {
  OBSERVATION_CATEGORIES,
  filteredOptions,
  groupedOptions,
  summaryCards,
  type Category,
  type ObservationFilters,
  type ObservationOption,
} from "./observationVocabulary";

const category = (code: string, id = code): Category => ({
  id,
  code,
  display_name: code,
  description: "",
  status: "active",
  display_order: 0,
  source: "platform_default",
});

const option = (
  code: string,
  source: ObservationOption["source"],
  overrides: Partial<ObservationOption> = {},
): ObservationOption => ({
  id: code,
  category_id: "emotion",
  organization_id: source === "platform_default" ? null : "org-a",
  code,
  display_name: code.endsWith("calm") ? "平靜" : "自訂情緒",
  description: "日常觀察說明",
  status: "active",
  enabled: true,
  display_order: 0,
  requires_note: false,
  source,
  editable: source === "organization_extension",
  has_historical_usage: false,
  historical_usage_count: 0,
  last_modified_at: "2026-08-11T00:00:00Z",
  last_modified_by: null,
  updated_at: "2026-08-11T00:00:00Z",
  ...overrides,
});

describe("observation vocabulary selectors", () => {
  it("keeps the fixed 13-category Traditional Chinese vocabulary", () => {
    expect(OBSERVATION_CATEGORIES).toHaveLength(13);
    expect(OBSERVATION_CATEGORIES[0]).toEqual(["care_completion", "照護完成"]);
    expect(OBSERVATION_CATEGORIES[12]).toEqual([
      "appearance_special_status",
      "外觀／特殊狀態",
    ]);
  });

  it("groups custom options before platform defaults without changing platform order", () => {
    const groups = groupedOptions(
      [category("emotion")],
      [
        option("emotion.platform", "platform_default", { display_order: 1 }),
        option("emotion.custom", "organization_extension", {
          display_order: 0,
        }),
      ],
      { search: "", category: "all", status: "all", source: "all" },
    );

    expect(groups[0].custom.map((item) => item.code)).toEqual([
      "emotion.custom",
    ]);
    expect(groups[0].platform.map((item) => item.code)).toEqual([
      "emotion.platform",
    ]);
  });

  it("combines case-insensitive text, category, status and source filters", () => {
    const filters: ObservationFilters = {
      search: "CALM",
      category: "emotion",
      status: "disabled",
      source: "organization_extension",
    };
    const options = [
      option("emotion.calm", "organization_extension", {
        status: "disabled",
        enabled: false,
      }),
      option("emotion.calm.default", "platform_default"),
    ];

    expect(filteredOptions(options, filters).map((item) => item.code)).toEqual([
      "emotion.calm",
    ]);
  });

  it("returns four management summary cards and two read-only cards for Staff", () => {
    expect(
      summaryCards({
        scope: "admin_full",
        category_count: 13,
        active_option_count: 42,
        custom_option_count: 3,
        inactive_option_count: 2,
      }),
    ).toHaveLength(4);
    expect(
      summaryCards({
        scope: "staff_active",
        category_count: 13,
        active_option_count: 42,
      }),
    ).toHaveLength(2);
  });
});
