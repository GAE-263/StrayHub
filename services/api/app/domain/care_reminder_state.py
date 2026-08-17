from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from services.api.app.api.errors import DomainError

TERMINAL_STATUSES = {"completed", "skipped", "cancelled"}
VALID_ACTIONS = {"completed", "skipped", "cancelled", "rescheduled"}


@dataclass(frozen=True)
class ReminderActionDecision:
    status: str
    actual_completed_at: datetime | None = None


def decide_reminder_action(
    *,
    current_status: str,
    action: str,
    recorded_at: datetime,
    reason: str | None = None,
    scheduled_at: datetime | None = None,
    actual_completed_at: datetime | None = None,
) -> ReminderActionDecision:
    if current_status in TERMINAL_STATUSES:
        raise DomainError("occurrence_terminal", "提醒已完成或結束，無法重複處理", 409)
    if current_status != "pending" or action not in VALID_ACTIONS:
        raise DomainError("invalid_occurrence_action", "提醒處理動作無效", 422)
    if action in {"skipped", "cancelled", "rescheduled"} and not (reason or "").strip():
        raise DomainError("reminder_action_reason_required", "此操作需要填寫原因", 422)
    if action == "rescheduled":
        if scheduled_at is None:
            raise DomainError("reschedule_time_required", "改期需要新的執行時間", 422)
        return ReminderActionDecision("pending")
    if action == "completed":
        actual = actual_completed_at or recorded_at
        if actual.tzinfo is None:
            actual = actual.replace(tzinfo=timezone.utc)
        if actual > recorded_at + timedelta(minutes=5):
            raise DomainError("actual_completed_at_invalid", "實際完成時間不可晚於回報時間", 422)
        return ReminderActionDecision("completed", actual.astimezone(timezone.utc))
    return ReminderActionDecision(action)
