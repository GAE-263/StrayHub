import type { AgendaItem } from "./types";

export function mapAgendaItem(value: Record<string, unknown>): AgendaItem {
  return {
    occurrence_id: String(value.occurrence_id ?? ""),
    animal_id: String(value.animal_id ?? ""),
    animal_name: String(value.animal_name ?? ""),
    shelter_number:
      value.shelter_number == null ? null : String(value.shelter_number),
    reminder_type: String(value.reminder_type ?? "other"),
    title: String(value.title ?? ""),
    instructions: String(value.instructions ?? ""),
    scheduled_at: String(value.scheduled_at ?? ""),
    status: (value.status as AgendaItem["status"]) ?? "pending",
    version: Number(value.version ?? 0),
    is_virtual: Boolean(value.is_virtual),
    assignee_membership_id:
      value.assignee_membership_id == null
        ? null
        : String(value.assignee_membership_id),
  };
}
