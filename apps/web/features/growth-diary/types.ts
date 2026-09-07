import type { components } from "../../../../packages/contracts/src/openapi";

export type GrowthDiaryAiSummary =
  components["schemas"]["GrowthDiaryAiSummary"];
export type GrowthDiaryAiProvenance =
  components["schemas"]["GrowthDiaryAiProvenance"];
type GeneratedGrowthDiaryListItem =
  components["schemas"]["GrowthDiaryListItem"];
export type GrowthDiaryListItem = GeneratedGrowthDiaryListItem & {
  photo_endpoints?: string[];
  entry_date?: string;
  status?: "new" | "reviewed";
  status_updated_at?: string | null;
};
export type GrowthDiaryDetail = components["schemas"]["GrowthDiaryDetail"] &
  GrowthDiaryListItem;
export type GrowthDiaryListResponse = Omit<
  components["schemas"]["GrowthDiaryListResponse"],
  "items"
> & { items: GrowthDiaryListItem[] };

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
