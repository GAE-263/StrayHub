import type { components } from "../../../../packages/contracts/src/openapi";

export type AssignedCareItem = components["schemas"]["AssignedCareItem"];
export type AssignedCareMutation =
  components["schemas"]["AssignedCareMutation"];
export type AssignedCareAction = components["schemas"]["AssignedCareAction"];
export type MedicalRecord = components["schemas"]["MedicalRecord"];
export type MedicalRecordPage = components["schemas"]["MedicalRecordPage"];

export type ReminderSeries = components["schemas"]["CareReminderSeries"];

export type ReminderSeriesPayload =
  components["schemas"]["CareReminderSeriesCreate"];

export type ReminderStopPayload = components["schemas"]["ReminderStop"];

export type ReminderOccurrenceEdit = components["schemas"]["OccurrenceEdit"];

export type AgendaBucket =
  "today_pending" | "overdue" | "today_resolved" | "next_seven_days";

export type AgendaItem = {
  occurrence_id: string;
  animal_id: string;
  animal_name: string;
  shelter_number: string | null;
  reminder_type: string;
  title: string;
  instructions: string;
  scheduled_at: string;
  status: "pending" | "completed" | "skipped" | "cancelled";
  version: number;
  is_virtual: boolean;
  assignee_membership_id: string | null;
};

export type CareAgenda = {
  timezone: string;
  timezone_version: number;
  local_today: string;
  buckets: Record<AgendaBucket, AgendaItem[]>;
  totals: Record<AgendaBucket, number>;
  pages?: Record<
    AgendaBucket,
    {
      items: AgendaItem[];
      total_count: number;
      next_cursor: string | null;
    }
  >;
};

export type CareCalendar = {
  organization_timezone: string;
  timezone_version: number;
  date_from: string;
  date_to: string;
  days: Array<{ local_date: string; items: unknown[] }>;
  total_count: number;
  next_cursor: string | null;
};
