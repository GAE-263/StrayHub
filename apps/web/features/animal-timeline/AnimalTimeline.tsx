"use client";

import React, { useState } from "react";
import { statusSummary } from "../../components/management/ui-status";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../components/management/StateViews";
import { TimelineDaySection } from "./TimelineDaySection";

type ObservationSnapshot = {
  code?: string;
  displayName?: string;
};

export type StoolAnalysis = {
  recognized: boolean;
  score?: number | null;
  scoreLabel?: string | null;
  hasAbnormalities: boolean;
  abnormalityDetails?: string | null;
  assessment?: string | null;
  recommendation?: string | null;
  reviewStatus?: string;
  humanReviewed: boolean;
};

export type TimelineDay = {
  date: string;
  hasReport: boolean;
  reportCount: number;
  reports?: Array<{
    id: string;
    submittedAt?: string;
    volunteerUserId?: string;
    note?: string | null;
    observations?: Record<string, string>;
    observationSnapshots?: Record<string, ObservationSnapshot>;
    mediaIds?: string[];
    aiJobStatus?: string;
    status?: string;
    stoolAnalysis?: StoolAnalysis | null;
  }>;
  events?: Array<{
    id: string;
    kind: string;
    title: string;
    summary?: string | null;
    happenedAt?: string;
    occurrence?: "actual" | "scheduled";
  }>;
  scheduled?: Array<{
    id: string;
    title: string;
    status?: string;
    scheduledAt?: string;
  }>;
};

type Props = {
  days: TimelineDay[];
  loading?: boolean;
  error?: string;
};

const OBSERVATION_LABELS: Record<string, string> = {
  care_completion: "照護完成狀態",
  walk_completion: "散步完成狀態",
  feeding: "進食",
  water: "飲水",
  activity: "活動",
  urination: "排尿",
  defecation: "排便",
  resource_guarding: "護食或資源防衛",
  human_interaction: "對人的互動",
  animal_interaction: "對其他動物的互動",
  emotion: "情緒",
  walk_reaction: "散步反應",
  appearance_special_status: "外觀／特殊狀態",
};

const OBSERVATION_VALUE_LABELS: Record<string, string> = {
  not_observed: "未觀察",
  uncertain: "無法判斷",
};

// 人工覆核後的三種終態；其餘（pending/succeeded/…）都還在等人看。
const STOOL_REVIEW_LABELS: Record<string, string> = {
  confirmed: "人工已確認",
  rejected: "人工已拒絕",
  corrected: "人工已修正",
};

function stoolAnalysisSummary(analysis: StoolAnalysis): string {
  if (!analysis.recognized) return "照片無法辨識，未產生判讀";
  const score =
    analysis.score != null
      ? `${analysis.score}/7 ${analysis.scoreLabel ?? ""}`.trim()
      : (analysis.scoreLabel ?? "—");
  return score;
}

function observationEntries(
  observations: Record<string, string> | undefined,
  snapshots: Record<string, ObservationSnapshot> | undefined,
) {
  return Object.entries(observations ?? {}).map(([key, code]) => {
    const snapshot = snapshots?.[key];
    const fallbackValue = code.split(".").at(-1) ?? code;
    return {
      key,
      label: OBSERVATION_LABELS[key] ?? key,
      value:
        snapshot?.displayName ??
        OBSERVATION_VALUE_LABELS[fallbackValue] ??
        code,
    };
  });
}

export function AnimalTimeline({ days, loading = false, error }: Props) {
  const [expandedDate, setExpandedDate] = useState<string | null>(null);

  if (loading) return <LoadingState title="正在載入動物歷程…" />;
  if (error) return <ErrorState title="歷程載入失敗" description={error} />;
  if (days.length === 0) return <EmptyState title="目前沒有可顯示的歷程" />;

  return (
    <ol aria-label="動物近 14 天歷程">
      {days.map((day) => (
        <TimelineDaySection
          key={day.date}
          date={day.date}
          hasReport={day.hasReport}
          reportCount={day.reportCount}
          events={[
            ...(day.scheduled ?? []).map((item) => ({
              ...item,
              kind: "care_reminder",
              occurrence: "scheduled" as const,
            })),
            ...(day.events ?? []).map((event) => ({
              ...event,
              occurrence: "actual" as const,
            })),
          ]}
          reportsExpanded={expandedDate === day.date}
          onToggleReports={() =>
            setExpandedDate((current) =>
              current === day.date ? null : day.date,
            )
          }
          reports={day.reports?.map((report) => {
            const entries = observationEntries(
              report.observations,
              report.observationSnapshots,
            );
            return (
              <article
                className="ui-card timeline-report"
                key={report.id}
                aria-label={`回報 ${report.id}`}
              >
                <p>
                  回報時間：{report.submittedAt ?? "未提供"}
                  {report.volunteerUserId
                    ? `；回報者：${report.volunteerUserId}`
                    : ""}
                </p>
                <p>心得：{report.note ?? "沒有心得"}</p>
                <p>結構化觀察：{entries.length} 項</p>
                {entries.length > 0 ? (
                  <dl aria-label="結構化觀察答案" className="detail-list">
                    {entries.map((entry) => (
                      <div key={entry.key}>
                        <dt>{entry.label}</dt>
                        <dd>{entry.value}</dd>
                      </div>
                    ))}
                  </dl>
                ) : null}
                <p>照片：{report.mediaIds?.length ?? 0} 張</p>
                {report.stoolAnalysis ? (
                  <section aria-label="AI 便便判讀">
                    <p>
                      AI 便便判讀：{stoolAnalysisSummary(report.stoolAnalysis)}
                      （
                      {STOOL_REVIEW_LABELS[
                        report.stoolAnalysis.reviewStatus ?? ""
                      ] ?? "待人工覆核"}
                      ）
                    </p>
                    {report.stoolAnalysis.hasAbnormalities ? (
                      <p>
                        ⚠️ 異常：
                        {report.stoolAnalysis.abnormalityDetails ?? "有異狀"}
                      </p>
                    ) : null}
                    {report.stoolAnalysis.recognized &&
                    report.stoolAnalysis.recommendation ? (
                      <p className="muted">
                        建議：{report.stoolAnalysis.recommendation}
                        （日常照護參考，不具醫療診斷效力）
                      </p>
                    ) : null}
                  </section>
                ) : null}
                <p>AI 處理：{statusSummary(report.aiJobStatus)}</p>
                <p>人工資料狀態：{statusSummary(report.status)}</p>
              </article>
            );
          })}
        />
      ))}
    </ol>
  );
}
