import type { components } from "../../../../packages/contracts/src/openapi";

export type GrowthDiaryAiSummary =
  components["schemas"]["GrowthDiaryAiSummary"];
export type GrowthDiaryAiProvenance =
  components["schemas"]["GrowthDiaryAiProvenance"];
export type GrowthDiaryListItem = components["schemas"]["GrowthDiaryListItem"];
export type GrowthDiaryDetail = components["schemas"]["GrowthDiaryDetail"];
export type GrowthDiaryListResponse =
  components["schemas"]["GrowthDiaryListResponse"];

export type GrowthDiaryMoodFilter =
  "all" | "concern" | "positive" | "neutral" | "unanalyzed";

export type GrowthDiaryListQuery = {
  query?: string;
  mood?: GrowthDiaryMoodFilter;
  page?: number;
  pageSize?: number;
};
