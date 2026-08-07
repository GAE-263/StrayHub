import React from "react";

type TimelineDay = {
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

export function AnimalTimeline({ days }: { days: TimelineDay[] }) {
  return (
    <ol aria-label="動物近 14 天歷程">
      {days.map((day) => (
        <li key={day.date}>
          <h3>{day.date}</h3>
          {day.hasReport ? (
            <p>有回報：{day.reportCount} 筆</p>
          ) : (
            <p>當日無回報</p>
          )}
          {day.reports?.map((report) => (
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
