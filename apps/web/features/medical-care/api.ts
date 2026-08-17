import { apiFetch } from "../../lib/api";
import type {
  AssignedCareAction,
  AssignedCareItem,
  AssignedCareMutation,
  CareAgenda,
  AgendaBucket,
  CareCalendar,
  MedicalRecord,
  MedicalRecordPage,
  ReminderOccurrenceEdit,
  ReminderSeries,
  ReminderSeriesPayload,
  ReminderStopPayload,
} from "./types";

export type MedicalRecordPayload = {
  occurred_at: string;
  record_type: string;
  title: string;
  content: string;
  clinic?: string;
  veterinarian?: string;
  weight_kg?: number | null;
  media_ids?: string[];
};

export async function createMedicalRecord(
  animalId: string,
  payload: MedicalRecordPayload,
): Promise<MedicalRecord> {
  return expectJson(
    await apiFetch(`/v1/management/animals/${animalId}/medical-records`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
    "醫療紀錄儲存失敗",
  );
}

async function expectJson<T>(response: Response, message: string): Promise<T> {
  if (!response.ok) {
    const error = new Error(
      response.status === 409
        ? "資料已被其他人更新，請重新載入。"
        : `${message}（HTTP ${response.status}）`,
    );
    Object.assign(error, { status: response.status });
    throw error;
  }
  return (await response.json()) as T;
}

export async function createReminderSeries(
  animalId: string,
  payload: ReminderSeriesPayload,
): Promise<ReminderSeries> {
  return expectJson(
    await apiFetch(`/v1/management/animals/${animalId}/care-reminder-series`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
    "提醒建立失敗",
  );
}

export async function fetchReminderSeries(
  seriesId: string,
): Promise<ReminderSeries> {
  return expectJson(
    await apiFetch(`/v1/management/care-reminder-series/${seriesId}`),
    "提醒載入失敗",
  );
}

export async function fetchMedicalRecords(
  animalId: string,
  params: {
    occurredFrom?: string;
    occurredTo?: string;
    recordType?: string;
    search?: string;
    includeArchived?: boolean;
  } = {},
  signal?: AbortSignal,
): Promise<MedicalRecordPage> {
  const query = new URLSearchParams();
  if (params.occurredFrom) query.set("occurred_from", params.occurredFrom);
  if (params.occurredTo) query.set("occurred_to", params.occurredTo);
  if (params.recordType) query.set("record_type", params.recordType);
  if (params.search) query.set("search", params.search);
  if (params.includeArchived) query.set("include_archived", "true");
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return expectJson(
    await apiFetch(
      `/v1/management/animals/${animalId}/medical-records${suffix}`,
      { signal },
    ),
    "醫療歷史載入失敗",
  );
}

export async function updateMedicalRecord(
  recordId: string,
  payload: {
    expected_version: number;
    title?: string;
    content?: string;
    record_type?: string;
    occurred_at?: string;
    clinic?: string | null;
    veterinarian?: string | null;
    weight_kg?: number | null;
    reason: string;
  },
): Promise<MedicalRecord> {
  return expectJson(
    await apiFetch(`/v1/management/medical-records/${recordId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
    "醫療紀錄更新失敗",
  );
}

export async function archiveMedicalRecord(
  recordId: string,
  payload: { expected_version: number; reason: string },
): Promise<MedicalRecord> {
  return expectJson(
    await apiFetch(`/v1/management/medical-records/${recordId}/archive`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
    "醫療紀錄封存失敗",
  );
}

export async function stopReminderSeries(
  seriesId: string,
  payload: ReminderStopPayload,
): Promise<ReminderSeries> {
  return expectJson(
    await apiFetch(`/v1/management/care-reminder-series/${seriesId}/stop`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
    "提醒停止失敗",
  );
}

export async function editReminderOccurrence(
  occurrenceId: string,
  payload: ReminderOccurrenceEdit,
): Promise<Response> {
  const response = await apiFetch(
    `/v1/management/care-reminder-occurrences/${occurrenceId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) throw new Error("提醒修改失敗，請重新載入最新狀態。");
  return response;
}

export async function fetchCareCalendar(
  dateFrom: string,
  dateTo: string,
  signal?: AbortSignal,
): Promise<CareCalendar> {
  const query = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
  return expectJson(
    await apiFetch(`/v1/management/care-calendar?${query}`, { signal }),
    "照護行事曆載入失敗",
  );
}

export async function fetchCareAgenda(
  params: {
    date?: string;
    animalId?: string;
    reminderType?: string;
    status?: string;
    assigneeMembershipId?: string;
    pageSize?: number;
    cursors?: Partial<Record<AgendaBucket, string>>;
  } = {},
  signal?: AbortSignal,
): Promise<CareAgenda> {
  const query = new URLSearchParams();
  if (params.date) query.set("date", params.date);
  if (params.animalId) query.set("animal_id", params.animalId);
  if (params.reminderType) query.set("reminder_type", params.reminderType);
  if (params.status) query.set("status", params.status);
  if (params.assigneeMembershipId)
    query.set("assignee_membership_id", params.assigneeMembershipId);
  query.set("page_size", String(params.pageSize ?? 100));
  for (const [bucket, cursor] of Object.entries(params.cursors ?? {})) {
    if (cursor) query.set(`${bucket}_cursor`, cursor);
  }
  const response = await apiFetch(`/v1/management/care-agenda?${query}`, {
    signal,
  });
  if (!response.ok)
    throw new Error(`照護行事曆載入失敗（HTTP ${response.status}）`);
  return (await response.json()) as CareAgenda;
}

export async function actOnReminder(
  occurrenceId: string,
  payload: {
    action: "completed" | "skipped" | "cancelled" | "rescheduled";
    expected_version: number;
    reason?: string;
    result_note?: string;
    scheduled_at?: string;
    actual_completed_at?: string;
  },
) {
  const response = await apiFetch(
    `/v1/management/care-reminder-occurrences/${occurrenceId}/actions`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const error = new Error(
      response.status === 409
        ? "此提醒已被其他人更新，請重新載入後確認。"
        : `提醒處理失敗（HTTP ${response.status}）`,
    );
    Object.assign(error, { status: response.status });
    throw error;
  }
  return response.json();
}

export async function fetchAssignedCare(
  occurrenceId: string,
  signal?: AbortSignal,
): Promise<AssignedCareItem> {
  const response = await apiFetch(
    `/v1/assigned-care-reminders/${occurrenceId}`,
    { signal },
  );
  if (!response.ok) {
    throw new Error(
      response.status === 404
        ? "找不到這筆指派事項，可能已改派或權限已失效。"
        : `指派事項載入失敗（HTTP ${response.status}）`,
    );
  }
  return (await response.json()) as AssignedCareItem;
}

export async function actOnAssignedCare(
  occurrenceId: string,
  payload: AssignedCareAction,
): Promise<AssignedCareMutation> {
  const response = await apiFetch(
    `/v1/assigned-care-reminders/${occurrenceId}/actions`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const message =
      response.status === 404
        ? "這筆事項已改派或權限已失效。"
        : response.status === 409
          ? "這筆事項已被其他人處理，請重新載入。"
          : `指派事項處理失敗（HTTP ${response.status}）`;
    const error = new Error(message);
    Object.assign(error, { status: response.status });
    throw error;
  }
  return (await response.json()) as AssignedCareMutation;
}
