export const OBSERVATION_CATEGORIES = [
  ["care_completion", "照護完成"],
  ["walk_completion", "散步完成"],
  ["feeding", "進食"],
  ["water", "飲水"],
  ["activity", "活動"],
  ["urination", "排尿"],
  ["defecation", "排便"],
  ["resource_guarding", "護食"],
  ["human_interaction", "人際互動"],
  ["animal_interaction", "動物互動"],
  ["emotion", "情緒"],
  ["walk", "散步"],
  ["appearance_special_status", "外觀／特殊狀態"],
] as const;

export type ObservationStatus = "active" | "disabled" | "archived";
export type ObservationSource = "platform_default" | "organization_extension";

export type Category = {
  id: string;
  code: string;
  display_name: string;
  description: string;
  status: string;
  display_order: number;
  source: ObservationSource;
};

export type ObservationOption = {
  id: string;
  category_id: string;
  organization_id: string | null;
  code: string;
  display_name: string;
  description: string;
  status: ObservationStatus;
  enabled: boolean;
  display_order: number;
  requires_note: boolean;
  source: ObservationSource;
  editable: boolean;
  has_historical_usage: boolean;
  historical_usage_count: number;
  last_modified_at: string;
  last_modified_by: string | null;
  updated_at: string;
};

export type Summary =
  | {
      scope: "admin_full";
      category_count: number;
      active_option_count: number;
      custom_option_count: number;
      inactive_option_count: number;
    }
  | {
      scope: "staff_active";
      category_count: number;
      active_option_count: number;
    };

export type CategoryCount = {
  category_id: string;
  active_count: number;
  custom_count?: number;
  inactive_count?: number;
};

export type ObservationList = {
  items: ObservationOption[];
  summary: Summary;
  category_counts: CategoryCount[];
};

export type ObservationFilters = {
  search: string;
  category: string;
  status: "all" | ObservationStatus;
  source: "all" | ObservationSource;
};

export const emptyFilters: ObservationFilters = {
  search: "",
  category: "all",
  status: "all",
  source: "all",
};

export function categoryLabel(category: Category): string {
  return (
    OBSERVATION_CATEGORIES.find(([code]) => code === category.code)?.[1] ??
    category.display_name
  );
}

export function optionSourceLabel(source: ObservationSource): string {
  return source === "platform_default" ? "平台預設" : "收容所自訂";
}

export function optionStatusLabel(status: ObservationStatus): string {
  if (status === "active") return "啟用中";
  if (status === "disabled") return "已停用";
  return "已封存";
}

export function matchesOption(
  option: ObservationOption,
  filters: ObservationFilters,
): boolean {
  const needle = filters.search.trim().toLocaleLowerCase();
  const text =
    `${option.display_name} ${option.code} ${option.description}`.toLocaleLowerCase();
  return (
    (!needle || text.includes(needle)) &&
    (filters.category === "all" || option.category_id === filters.category) &&
    (filters.status === "all" || option.status === filters.status) &&
    (filters.source === "all" || option.source === filters.source)
  );
}

export function filteredOptions(
  options: ObservationOption[],
  filters: ObservationFilters,
): ObservationOption[] {
  return options.filter((option) => matchesOption(option, filters));
}

export function groupedOptions(
  categories: Category[],
  options: ObservationOption[],
  filters: ObservationFilters,
) {
  const filtered = filteredOptions(options, filters);
  return categories
    .slice()
    .sort((a, b) => a.display_order - b.display_order)
    .map((category) => {
      const categoryOptions = filtered.filter(
        (item) => item.category_id === category.id,
      );
      const custom = categoryOptions
        .filter((item) => item.source === "organization_extension")
        .sort((a, b) => a.display_order - b.display_order);
      const platform = categoryOptions
        .filter((item) => item.source === "platform_default")
        .sort((a, b) => a.display_order - b.display_order);
      return { category, custom, platform };
    })
    .filter(({ custom, platform }) => custom.length > 0 || platform.length > 0);
}

export function summaryCards(summary: Summary) {
  if (summary.scope === "staff_active") {
    return [
      ["觀察類別", summary.category_count],
      ["啟用中的選項", summary.active_option_count],
    ] as const;
  }
  return [
    ["觀察類別", summary.category_count],
    ["啟用中的選項", summary.active_option_count],
    ["收容所自訂選項", summary.custom_option_count],
    ["已停用或封存", summary.inactive_option_count],
  ] as const;
}
