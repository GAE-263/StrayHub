import type { TimelineDay } from "./AnimalTimeline";

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
};

export type ApiDay = {
  date: string;
  has_report: boolean;
  report_count: number;
  reports?: ApiReport[];
};

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
    })),
  }));
}
