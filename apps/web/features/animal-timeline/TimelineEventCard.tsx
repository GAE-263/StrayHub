import React from "react";
import { DEFAULT_TIMELINE_TIMEZONE, localDateTime } from "./timelineFormat";

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

export function TimelineEventCard({
  event,
  timezone = DEFAULT_TIMELINE_TIMEZONE,
}: {
  event: TimelineEvent;
  timezone?: string;
}) {
  const actual = event.occurrence === "actual";
  return (
    <article
      className="ui-card timeline-event-card"
      data-occurrence={event.occurrence}
      aria-label={`${actual ? "已發生" : "預定"} ${event.title}`}
    >
      <p className="timeline-event-kind">
        {actual ? "已發生事件" : "預定照護"}
      </p>
      <p className="timeline-event-title">{event.title}</p>
      <dl className="timeline-field-grid">
        {actual ? (
          <div>
            <dt>發生時間</dt>
            <dd>{localDateTime(event.happenedAt, timezone) ?? "未提供"}</dd>
          </div>
        ) : (
          <>
            <div>
              <dt>狀態</dt>
              <dd>{event.status ?? "pending"}</dd>
            </div>
            <div>
              <dt>預定時間</dt>
              <dd>{localDateTime(event.scheduledAt, timezone) ?? "未提供"}</dd>
            </div>
          </>
        )}
      </dl>
      {event.summary ? (
        <p className="timeline-event-summary">{event.summary}</p>
      ) : null}
    </article>
  );
}
