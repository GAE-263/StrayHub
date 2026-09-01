import type { TimelineDay } from "./AnimalTimeline";
import type { TimelineEvent } from "./TimelineEventCard";

export type ApiReport = {
  id: string;
  submitted_at?: string;
  volunteer_user_id?: string;
  note?: string | null;
  observations?: Record<string, string>;
  observation_snapshots?: Record<string, Record<string, string>> | null;
  media_ids?: string[];
  ai_job_status?: string;
  status?: string;
  stool_analysis?: {
    recognized: boolean;
    score: number | null;
    score_label: string | null;
    has_abnormalities: boolean;
    abnormality_details: string | null;
    assessment: string | null;
    recommendation: string | null;
    review_status: string;
    human_reviewed: boolean;
  } | null;
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
      stoolAnalysis: report.stool_analysis
        ? {
            recognized: report.stool_analysis.recognized,
            score: report.stool_analysis.score,
            scoreLabel: report.stool_analysis.score_label,
            hasAbnormalities: report.stool_analysis.has_abnormalities,
            abnormalityDetails: report.stool_analysis.abnormality_details,
            assessment: report.stool_analysis.assessment,
            recommendation: report.stool_analysis.recommendation,
            reviewStatus: report.stool_analysis.review_status,
            humanReviewed: report.stool_analysis.human_reviewed,
          }
        : null,
    })),
    events: mapTimelineEvents(day).filter(
      (event) => event.occurrence === "actual",
    ),
    scheduled: mapTimelineEvents(day).filter(
      (event) => event.occurrence === "scheduled",
    ),
  }));
}
