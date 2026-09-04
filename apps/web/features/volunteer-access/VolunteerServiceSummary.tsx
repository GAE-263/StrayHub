"use client";

import React from "react";

import { Alert } from "../../components/ui/alert";

export type VolunteerExperienceSummary = {
  current_shelter_visits: number;
  total_strayhub_visits: number;
  visits_last_180_days: number;
  visits_last_90_days: number;
  visits_last_30_days: number;
  last_visit_at: string | null;
  active_months_last_6_months: number;
  recent_status:
    | "new"
    | "consistently_active"
    | "recently_active"
    | "less_recently_active"
    | "active";
  has_active_platform_restriction: boolean;
  approval_blocked: boolean;
};

const STATUS_LABELS: Record<
  VolunteerExperienceSummary["recent_status"],
  string
> = {
  new: "新加入",
  consistently_active: "持續參與",
  recently_active: "近期活躍",
  less_recently_active: "近期較少出現",
  active: "穩定參與",
};

export function VolunteerServiceSummary({
  summary,
  loading,
  error,
}: {
  summary: VolunteerExperienceSummary | null;
  loading: boolean;
  error: string;
}) {
  return (
    <section
      className="space-y-2 border-t pt-3"
      aria-labelledby="service-summary-title"
    >
      <h3 id="service-summary-title">StrayHub 志工經驗</h3>
      {loading ? <p role="status">正在計算服務經驗…</p> : null}
      {error ? <Alert role="alert">{error}</Alert> : null}
      {summary ? (
        <>
          <dl className="summary-grid">
            <div>
              <dt>累積服務</dt>
              <dd>{summary.total_strayhub_visits} 次</dd>
            </div>
            <div>
              <dt>本收容所</dt>
              <dd>{summary.current_shelter_visits} 次</dd>
            </div>
            <div>
              <dt>最近半年</dt>
              <dd>{summary.visits_last_180_days} 次</dd>
            </div>
            <div>
              <dt>最近三個月</dt>
              <dd>{summary.visits_last_90_days} 次</dd>
            </div>
            <div>
              <dt>最近服務</dt>
              <dd>
                {summary.last_visit_at
                  ? new Date(summary.last_visit_at).toLocaleDateString("zh-TW")
                  : "尚無紀錄"}
              </dd>
            </div>
            <div>
              <dt>近期狀態</dt>
              <dd>● {STATUS_LABELS[summary.recent_status]}</dd>
            </div>
          </dl>
          {summary.has_active_platform_restriction ? (
            <Alert role="alert">
              ⛔ 此志工目前有經正式確認且仍有效的 StrayHub
              志工服務限制，目前不可直接核准。
            </Alert>
          ) : (
            <p className="success-message">✓ 沒有需要注意的跨收容所服務限制</p>
          )}
        </>
      ) : null}
    </section>
  );
}
