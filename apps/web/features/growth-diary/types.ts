import type { components } from "../../../../packages/contracts/src/openapi";

export type GrowthDiaryAiSummary =
  components["schemas"]["GrowthDiaryAiSummary"];
export type GrowthDiaryAiProvenance =
  components["schemas"]["GrowthDiaryAiProvenance"];
type GeneratedGrowthDiaryListItem =
  components["schemas"]["GrowthDiaryListItem"];
export type GrowthDiaryListItem = Omit<
  GeneratedGrowthDiaryListItem,
  "photo_endpoints" | "entry_date" | "status" | "status_updated_at"
> & {
  photo_endpoints?: string[];
  entry_date?: string;
  status?: "new" | "reviewed";
  status_updated_at?: string | null;
};
export type GrowthDiaryDetail = Omit<
  components["schemas"]["GrowthDiaryDetail"],
  keyof GrowthDiaryListItem
> &
  GrowthDiaryListItem;
export type GrowthDiaryListResponse = Omit<
  components["schemas"]["GrowthDiaryListResponse"],
  "items"
> & { items: GrowthDiaryListItem[]; timezone: string };

export type GrowthDiaryMoodFilter =
  "all" | "concern" | "positive" | "neutral" | "unanalyzed";
export type GrowthDiaryStatusFilter = "all" | "new" | "reviewed";

export type GrowthDiaryListQuery = {
  query?: string;
  mood?: GrowthDiaryMoodFilter;
  status?: GrowthDiaryStatusFilter;
  fromDate?: string;
  toDate?: string;
  page?: number;
  pageSize?: number;
};
