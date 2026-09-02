"use client";

import Link from "next/link";
import React, { useState } from "react";
import { statusSummary } from "../../components/management/ui-status";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../components/management/StateViews";
import { TimelineDaySection } from "./TimelineDaySection";
import { DEFAULT_TIMELINE_TIMEZONE, localDateTime } from "./timelineFormat";

type ObservationSnapshot = {
  code?: string;
  displayName?: string;
};

export type TimelineDay = {
  date: string;
  hasReport: boolean;
  reportCount: number;
  reports?: Array<{
    id: string;
    submittedAt?: string;
    volunteerUserId?: string;
    volunteerLabel?: string | null;
    note?: string | null;
    observations?: Record<string, string>;
    observationSnapshots?: Record<string, ObservationSnapshot>;
    mediaIds?: string[];
    aiJobStatus?: string;
    status?: string;
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
  timezone?: string;
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

export function AnimalTimeline({
  days,
  loading = false,
  error,
  timezone = DEFAULT_TIMELINE_TIMEZONE,
}: Props) {
  const [expandedDate, setExpandedDate] = useState<string | null>(null);

  if (loading) return <LoadingState title="正在載入動物歷程…" />;
  if (error) return <ErrorState title="歷程載入失敗" description={error} />;
  if (days.length === 0) return <EmptyState title="目前沒有可顯示的歷程" />;

  return (
    <ol className="animal-timeline" aria-label="動物近 14 天歷程">
      {days.map((day) => (
        <TimelineDaySection
          key={day.date}
          timezone={timezone}
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
                <header className="timeline-report-head">
                  <span className="timeline-report-time">
                    {localDateTime(report.submittedAt, timezone) ??
                      "回報時間未提供"}
                  </span>
                  {report.volunteerUserId ? (
                    <Link
                      className="timeline-report-author"
                      href={`/volunteers/access?user_id=${report.volunteerUserId}`}
                    >
                      回報者：
                      {report.volunteerLabel ??
                        `志工 #${report.volunteerUserId.slice(0, 8)}`}
                    </Link>
                  ) : null}
                </header>
                <dl className="timeline-field-grid">
                  <div>
                    <dt>AI 處理</dt>
                    <dd>{statusSummary(report.aiJobStatus)}</dd>
                  </div>
                  <div>
                    <dt>人工資料狀態</dt>
                    <dd>{statusSummary(report.status)}</dd>
                  </div>
                  <div>
                    <dt>照片</dt>
                    <dd>{report.mediaIds?.length ?? 0} 張</dd>
                  </div>
                  <div>
                    <dt>結構化觀察</dt>
                    <dd>{entries.length} 項</dd>
                  </div>
                </dl>
                <p className="timeline-report-note">
                  心得：{report.note ?? "沒有心得"}
                </p>
                {entries.length > 0 ? (
                  <dl
                    aria-label="結構化觀察答案"
                    className="timeline-observation-grid"
                  >
                    {entries.map((entry) => (
                      <div key={entry.key}>
                        <dt>{entry.label}</dt>
                        <dd>{entry.value}</dd>
                      </div>
                    ))}
                  </dl>
                ) : null}
              </article>
            );
          })}
        />
      ))}
    </ol>
  );
}
