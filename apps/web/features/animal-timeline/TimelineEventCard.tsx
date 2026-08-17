import React from "react";

export type TimelineEvent = {
  id: string;
  kind: string;
  title: string;
  summary?: string | null;
  happenedAt?: string;
  scheduledAt?: string;
  status?: string;
  occurrence: "actual" | "scheduled";
};

export function TimelineEventCard({ event }: { event: TimelineEvent }) {
  const actual = event.occurrence === "actual";
  return (
    <article
      className="ui-card timeline-report"
      aria-label={`${actual ? "已發生" : "預定"} ${event.title}`}
    >
      <p>
        <strong>{actual ? "已發生事件" : "預定照護"}</strong> · {event.title}
      </p>
      <p>
        {actual
          ? (event.happenedAt ?? "發生時間未提供")
          : `狀態：${event.status ?? "pending"}；預定時間：${event.scheduledAt ?? "未提供"}`}
      </p>
      {event.summary ? <p>{event.summary}</p> : null}
    </article>
  );
}
