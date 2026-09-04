import React from "react";
import { Badge } from "../../components/ui/badge";
import { TimelineEventCard, type TimelineEvent } from "./TimelineEventCard";

export type TimelineDaySectionProps = {
  date: string;
  hasReport: boolean;
  reportCount: number;
  events: TimelineEvent[];
  reports?: React.ReactNode;
  onToggleReports?: () => void;
  reportsExpanded?: boolean;
  timezone?: string;
};

const WEEKDAYS = ["週日", "週一", "週二", "週三", "週四", "週五", "週六"];

function weekdayLabel(date: string) {
  const parsed = new Date(`${date}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return "";
  return WEEKDAYS[parsed.getDay()];
}

export function TimelineDaySection({
  date,
  hasReport,
  reportCount,
  events,
  reports,
  onToggleReports,
  reportsExpanded = false,
  timezone,
}: TimelineDaySectionProps) {
  const scheduled = events.filter((event) => event.occurrence === "scheduled");
  const actual = events.filter((event) => event.occurrence === "actual");
  const weekday = weekdayLabel(date);
  const quiet = !hasReport && events.length === 0;
  return (
    <li className="timeline-day" data-quiet={quiet ? "true" : undefined}>
      <div className="timeline-day-rail">
        <h3 className="timeline-day-date">{date}</h3>
        {weekday ? (
          <span className="timeline-day-weekday">{weekday}</span>
        ) : null}
        {quiet ? null : (
          <div className="timeline-day-counts">
            {hasReport ? <Badge>回報 {reportCount}</Badge> : null}
            {actual.length > 0 ? <Badge>事件 {actual.length}</Badge> : null}
            {scheduled.length > 0 ? (
              <Badge data-tone="scheduled">待辦 {scheduled.length}</Badge>
            ) : null}
          </div>
        )}
      </div>
      <div className="timeline-day-body">
        {scheduled.length > 0 ? (
          <section
            className="timeline-day-group"
            aria-label={`${date} 預定照護`}
          >
            <h4 className="timeline-group-title">待辦與預定</h4>
            <div className="timeline-card-grid">
              {scheduled.map((event) => (
                <TimelineEventCard
                  key={`scheduled-${event.id}`}
                  event={event}
                  timezone={timezone}
                />
              ))}
            </div>
          </section>
        ) : null}
        {actual.length > 0 ? (
          <section
            className="timeline-day-group"
            aria-label={`${date} 已發生事件`}
          >
            <h4 className="timeline-group-title">已發生事件</h4>
            <div className="timeline-card-grid">
              {actual.map((event) => (
                <TimelineEventCard
                  key={`event-${event.id}`}
                  event={event}
                  timezone={timezone}
                />
              ))}
            </div>
          </section>
        ) : null}
        {hasReport ? (
          <section
            className="timeline-day-group"
            aria-label={`${date} 志工回報`}
          >
            <button
              className="ui-button ui-button-ghost timeline-report-toggle"
              type="button"
              aria-expanded={reportsExpanded}
              onClick={onToggleReports}
            >
              有回報：{reportCount} 筆
              <span aria-hidden="true">{reportsExpanded ? "▴" : "▾"}</span>
            </button>
            {reportsExpanded ? (
              <div className="timeline-card-grid timeline-report-grid">
                {reports}
              </div>
            ) : null}
          </section>
        ) : null}
        {quiet ? <p className="timeline-day-empty">當日沒有事件</p> : null}
        {!hasReport && events.length > 0 && actual.length === 0 ? (
          <p className="timeline-day-empty">當日沒有志工回報</p>
        ) : null}
      </div>
    </li>
  );
}
