import React from "react";
import { TimelineEventCard, type TimelineEvent } from "./TimelineEventCard";

export type TimelineDaySectionProps = {
  date: string;
  hasReport: boolean;
  reportCount: number;
  events: TimelineEvent[];
  reports?: React.ReactNode;
  onToggleReports?: () => void;
  reportsExpanded?: boolean;
};

export function TimelineDaySection({
  date,
  hasReport,
  reportCount,
  events,
  reports,
  onToggleReports,
  reportsExpanded = false,
}: TimelineDaySectionProps) {
  const scheduled = events.filter((event) => event.occurrence === "scheduled");
  const actual = events.filter((event) => event.occurrence === "actual");
  return (
    <li>
      <h3>{date}</h3>
      {scheduled.length > 0 ? (
        <section aria-label={`${date} 預定照護`}>
          <h4>待辦與預定</h4>
          {scheduled.map((event) => (
            <TimelineEventCard key={`scheduled-${event.id}`} event={event} />
          ))}
        </section>
      ) : null}
      {hasReport ? (
        <button
          className="ui-button ui-button-ghost"
          type="button"
          aria-expanded={reportsExpanded}
          onClick={onToggleReports}
        >
          有回報：{reportCount} 筆
        </button>
      ) : null}
      {actual.length > 0 ? (
        <section aria-label={`${date} 已發生事件`}>
          <h4>已發生事件</h4>
          {actual.map((event) => (
            <TimelineEventCard key={`event-${event.id}`} event={event} />
          ))}
        </section>
      ) : null}
      {!hasReport && events.length === 0 ? <p>當日沒有事件</p> : null}
      {!hasReport && events.length > 0 && actual.length === 0 ? (
        <p>當日沒有志工回報</p>
      ) : null}
      {reportsExpanded ? reports : null}
    </li>
  );
}
