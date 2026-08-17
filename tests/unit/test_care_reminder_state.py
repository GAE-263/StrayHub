from datetime import datetime, timedelta, timezone

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.domain.care_reminder_state import decide_reminder_action

NOW = datetime(2026, 8, 16, 4, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("action", "expected"),
    (("completed", "completed"), ("skipped", "skipped"), ("cancelled", "cancelled")),
)
def test_pending_can_reach_terminal_states(action: str, expected: str) -> None:
    decision = decide_reminder_action(
        current_status="pending",
        action=action,
        recorded_at=NOW,
        reason="人工確認" if action != "completed" else None,
    )
    assert decision.status == expected


def test_complete_defaults_actual_time_to_server_recorded_time() -> None:
    decision = decide_reminder_action(current_status="pending", action="completed", recorded_at=NOW)
    assert decision.actual_completed_at == NOW


def test_future_actual_time_over_five_minutes_is_rejected() -> None:
    with pytest.raises(DomainError, match="不可晚於回報時間"):
        decide_reminder_action(
            current_status="pending",
            action="completed",
            recorded_at=NOW,
            actual_completed_at=NOW + timedelta(minutes=6),
        )


@pytest.mark.parametrize("action", ["skipped", "cancelled", "rescheduled"])
def test_reason_is_required_for_non_complete_actions(action: str) -> None:
    with pytest.raises(DomainError, match="需要填寫原因"):
        decide_reminder_action(
            current_status="pending",
            action=action,
            recorded_at=NOW,
            scheduled_at=NOW + timedelta(days=1) if action == "rescheduled" else None,
        )


def test_reschedule_remains_pending_and_terminal_cannot_be_reprocessed() -> None:
    decision = decide_reminder_action(
        current_status="pending",
        action="rescheduled",
        recorded_at=NOW,
        scheduled_at=NOW + timedelta(days=1),
        reason="等候回診",
    )
    assert decision.status == "pending"
    with pytest.raises(DomainError, match="無法重複處理"):
        decide_reminder_action(current_status="completed", action="completed", recorded_at=NOW)
