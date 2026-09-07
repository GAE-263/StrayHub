export function buildAnimalsQuery({
  page,
  query,
  status,
  areaId,
}: {
  page: number;
  query: string;
  status: string;
  areaId: string;
}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: "20",
    status,
  });
  if (query.trim()) params.set("query", query.trim());
  if (areaId) params.set("area_id", areaId);
  return params;
}

export type QrStatusFilter = "all" | "active" | "revoked";

export function buildQrCodesQuery({
  page,
  query,
  status,
  pageSize = 20,
}: {
  page: number;
  query: string;
  status: QrStatusFilter;
  pageSize?: number;
}) {
  const params = new URLSearchParams({
    page: String(Math.max(1, Math.floor(page))),
    page_size: String(pageSize),
    status,
  });
  const normalizedQuery = query.trim();
  if (normalizedQuery) params.set("query", normalizedQuery);
  return params;
}

export function buildReportsQuery({
  fromDate,
  toDate,
  status,
}: {
  fromDate: string;
  toDate: string;
  status: string;
}) {
  const params = new URLSearchParams({ page: "1", page_size: "50" });
  if (fromDate) params.set("from_date", fromDate);
  if (toDate) params.set("to_date", toDate);
  if (status) params.set("status", status);
  return params;
}

export function buildGrowthDiaryQuery({
  page,
  search,
  mood,
  status,
  fromDate,
  toDate,
  pageSize = 20,
}: {
  page: number;
  search: string;
  mood: string;
  status: string;
  fromDate: string;
  toDate: string;
  pageSize?: number;
}) {
  const params = new URLSearchParams({
    page: String(Math.max(1, Math.floor(page))),
    page_size: String(pageSize),
  });
  const normalizedSearch = search.trim();
  if (normalizedSearch) params.set("search", normalizedSearch);
  if (mood) params.set("mood", mood);
  if (status) params.set("status", status);
  if (fromDate) params.set("from_date", fromDate);
  if (toDate) params.set("to_date", toDate);
  return params;
}

export function buildAdoptionInquiryQuery({
  page,
  search,
  path,
  status,
  fromDate,
  toDate,
  pageSize = 20,
}: {
  page: number;
  search: string;
  path: string;
  status: string;
  fromDate: string;
  toDate: string;
  pageSize?: number;
}) {
  const params = new URLSearchParams({
    page: String(Math.max(1, Math.floor(page))),
    page_size: String(pageSize),
  });
  const normalizedSearch = search.trim();
  if (normalizedSearch) params.set("search", normalizedSearch);
  if (path) params.set("path", path);
  if (status) params.set("status", status);
  if (fromDate) params.set("from_date", fromDate);
  if (toDate) params.set("to_date", toDate);
  return params;
}

export function buildTimelineQuery(range: { start: string; end: string }) {
  const query = new URLSearchParams();
  if (range.start) query.set("start_date", range.start);
  if (range.end) query.set("end_date", range.end);
  return query;
}
