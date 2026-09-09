export type InquiryPath = "specific_animal" | "recommend_me";
export type InquiryStatus = "new" | "contacted";

export type AdoptionAnswerDisplay = {
  key: string;
  label: string;
  value: string;
};

export type AdoptionInquiry = {
  id: string;
  target_animal_id: string;
  animal_name: string;
  shelter_number: string | null;
  path: InquiryPath;
  adopter_name: string;
  phone_number: string;
  answers_display: AdoptionAnswerDisplay[];
  status: InquiryStatus;
  submitted_at: string;
  status_updated_at: string | null;
  ai_suitability_score: number | null;
  ai_suitability_explanation: string | null;
  ai_recommendation_overridden: boolean | null;
};

export type AdoptionInquiryListResponse = {
  items: AdoptionInquiry[];
  page: number;
  page_size: number;
  total: number;
};

export type AdoptionInquiryFilters = {
  page: number;
  search: string;
  path: string;
  status: string;
  fromDate: string;
  toDate: string;
};
