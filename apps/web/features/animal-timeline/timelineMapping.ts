import type { TimelineDay } from "./AnimalTimeline";
import type { TimelineEvent } from "./TimelineEventCard";

export type ApiReport = {
  id: string;
  submitted_at?: string;
  volunteer_user_id?: string;
  volunteer_label?: string | null;
  note?: string | null;
  observations?: Record<string, string>;
  observation_snapshots?: Record<string, Record<string, string>> | null;
  media_ids?: string[];
  ai_job_status?: string;
  status?: string;
};

export type ApiDay = {
  date: string;
  has_report: boolean;
  report_count: number;
  reports?: ApiReport[];
  events?: Array<{
    id: string;
    kind: string;
    title: string;
    summary?: string | null;
    happened_at?: string;
    occurrence?: "actual" | "scheduled";
  }>;
  scheduled?: Array<{
    id: string;
    title: string;
    status: string;
    scheduled_at?: string;
    occurrence?: "actual" | "scheduled";
  }>;
};

export function mapTimelineEvents(day: ApiDay): TimelineEvent[] {
  const actual = (day.events ?? []).map((event) => ({
    id: event.id,
    kind: event.kind,
    title: event.title,
    summary: event.summary,
    happenedAt: event.happened_at,
    occurrence: "actual" as const,
  }));
  const scheduled = (day.scheduled ?? []).map((item) => ({
    id: item.id,
    kind: "care_reminder",
    title: item.title,
    status: item.status ?? "pending",
    scheduledAt: item.scheduled_at,
    occurrence: "scheduled" as const,
  }));
  return [...scheduled, ...actual];
}

export function mapDays(days: ApiDay[]): TimelineDay[] {
  return days.map((day) => ({
    date: day.date,
    hasReport: day.has_report,
    reportCount: day.report_count,
    reports: day.reports?.map((report) => ({
      id: report.id,
      submittedAt: report.submitted_at,
      volunteerUserId: report.volunteer_user_id,
      volunteerLabel: report.volunteer_label,
      note: report.note,
      observations: report.observations,
      observationSnapshots: report.observation_snapshots
        ? Object.fromEntries(
            Object.entries(report.observation_snapshots).map(
              ([key, snapshot]) => [
                key,
                {
                  code: snapshot.code,
                  displayName: snapshot.display_name,
                },
              ],
            ),
          )
        : undefined,
      mediaIds: report.media_ids,
      aiJobStatus: report.ai_job_status,
      status: report.status,
    })),
    events: mapTimelineEvents(day).filter(
      (event) => event.occurrence === "actual",
    ),
    scheduled: mapTimelineEvents(day).filter(
      (event) => event.occurrence === "scheduled",
    ),
  }));
}
