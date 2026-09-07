import { buildAdoptionInquiryQuery } from "../../app/(management)/management-query";
import { authFetch } from "../../lib/auth";
import type {
  AdoptionInquiry,
  AdoptionInquiryFilters,
  AdoptionInquiryListResponse,
  InquiryStatus,
} from "./types";

export class AdoptionInquiryApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "AdoptionInquiryApiError";
  }
}

export async function fetchAdoptionInquiries(
  filters: AdoptionInquiryFilters,
  signal?: AbortSignal,
): Promise<AdoptionInquiryListResponse> {
  const query = buildAdoptionInquiryQuery(filters);
  const response = await authFetch(
    `/v1/management/adoption-inquiries?${query}`,
    { signal },
  );
  if (!response.ok) {
    throw new AdoptionInquiryApiError("領養意願載入失敗", response.status);
  }
  return (await response.json()) as AdoptionInquiryListResponse;
}

export async function updateAdoptionInquiryStatus(
  inquiryId: string,
  status: InquiryStatus,
): Promise<AdoptionInquiry> {
  const response = await authFetch(
    `/v1/management/adoption-inquiries/${encodeURIComponent(inquiryId)}/status`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    },
  );
  if (!response.ok) {
    throw new AdoptionInquiryApiError("狀態更新失敗", response.status);
  }
  const payload = (await response.json()) as { inquiry: AdoptionInquiry };
  return payload.inquiry;
}
