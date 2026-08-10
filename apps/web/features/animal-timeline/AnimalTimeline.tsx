"use client";

import React, { useState } from "react";

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
    note?: string | null;
    observations?: Record<string, string>;
    observationSnapshots?: Record<string, ObservationSnapshot>;
    mediaIds?: string[];
    aiJobStatus?: string;
    status?: string;
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

  if (loading) return <p role="status">正在載入動物歷程…</p>;
  if (error) return <p role="alert">歷程載入失敗：{error}</p>;
  if (days.length === 0) return <p>目前沒有可顯示的歷程。</p>;

  return (
    <ol aria-label="動物近 14 天歷程">
      {days.map((day) => (
        <li key={day.date}>
          <h3>{day.date}</h3>
          {day.hasReport ? (
            <button
              type="button"
              aria-expanded={expandedDate === day.date}
              onClick={() =>
                setExpandedDate((current) =>
                  current === day.date ? null : day.date,
                )
              }
            >
              有回報：{day.reportCount} 筆
            </button>
          ) : (
            <p>當日無回報</p>
          )}
          {expandedDate === day.date &&
            day.reports?.map((report) => {
              const entries = observationEntries(
                report.observations,
                report.observationSnapshots,
              );
              return (
                <article key={report.id} aria-label={`回報 ${report.id}`}>
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
                  <p>AI 處理：{report.aiJobStatus ?? "未提供"}</p>
                  <p>人工資料狀態：{report.status ?? "未提供"}</p>
                </article>
              );
            })}
        </li>
      ))}
    </ol>
  );
}
