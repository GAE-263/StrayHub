"use client";

import React, { useState } from "react";

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
            day.reports?.map((report) => (
              <article key={report.id} aria-label={`回報 ${report.id}`}>
                <p>
                  回報時間：{report.submittedAt ?? "未提供"}
                  {report.volunteerUserId
                    ? `；回報者：${report.volunteerUserId}`
                    : ""}
                </p>
                <p>心得：{report.note ?? "沒有心得"}</p>
                <p>
                  結構化觀察：{Object.keys(report.observations ?? {}).length} 項
                </p>
                <p>照片：{report.mediaIds?.length ?? 0} 張</p>
                <p>AI 處理：{report.aiJobStatus ?? "未提供"}</p>
                <p>人工資料狀態：{report.status ?? "未提供"}</p>
              </article>
            ))}
        </li>
      ))}
    </ol>
  );
}
