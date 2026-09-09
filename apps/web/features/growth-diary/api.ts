import { authFetch } from "../../lib/auth";
import type {
  GrowthDiaryDetail,
  GrowthDiaryListQuery,
  GrowthDiaryListResponse,
} from "./types";

export class GrowthDiaryApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "GrowthDiaryApiError";
  }
}

async function expectJson<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    throw new GrowthDiaryApiError(fallback, response.status);
  }
  return (await response.json()) as T;
}

export async function fetchGrowthDiaryEntries(
  query: GrowthDiaryListQuery = {},
  signal?: AbortSignal,
): Promise<GrowthDiaryListResponse> {
  const params = new URLSearchParams();
  const normalizedQuery = query.query?.trim();
  if (normalizedQuery) params.set("query", normalizedQuery);
  if (query.mood && query.mood !== "all") params.set("mood", query.mood);
  if (query.status && query.status !== "all")
    params.set("status", query.status);
  if (query.fromDate) params.set("from_date", query.fromDate);
  if (query.toDate) params.set("to_date", query.toDate);
  params.set("page", String(query.page ?? 1));
  params.set("page_size", String(query.pageSize ?? 50));

  return expectJson(
    await authFetch(`/v1/management/growth-diary-entries?${params}`, {
      signal,
    }),
    "毛孩日記載入失敗",
  );
}

export async function fetchGrowthDiaryDetail(
  entryId: string,
  signal?: AbortSignal,
): Promise<GrowthDiaryDetail> {
  return expectJson(
    await authFetch(
      `/v1/management/growth-diary-entries/${encodeURIComponent(entryId)}`,
      { signal },
    ),
    "AI 來源資訊載入失敗",
  );
}

export async function fetchGrowthDiaryPhoto(
  entryId: string,
  signal?: AbortSignal,
  photoIndex?: number,
): Promise<Blob> {
  const photoPath =
    photoIndex === undefined
      ? "photo"
      : `photos/${encodeURIComponent(photoIndex)}`;
  const response = await authFetch(
    `/v1/management/growth-diary-entries/${encodeURIComponent(entryId)}/${photoPath}`,
    { signal },
  );
  if (!response.ok) {
    throw new GrowthDiaryApiError("日記照片載入失敗", response.status);
  }
  return response.blob();
}

export async function updateGrowthDiaryStatus(
  entryId: string,
  status: "new" | "reviewed",
): Promise<GrowthDiaryDetail> {
  return expectJson(
    await authFetch(
      `/v1/management/growth-diary-entries/${encodeURIComponent(entryId)}/status`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      },
    ),
    "日記狀態更新失敗",
  );
}
