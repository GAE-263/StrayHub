from services.api.app.api.care_reminders import (
    OccurrenceActionRequest,
    OccurrenceEditRequest,
    SeriesCreateRequest,
    SeriesStopRequest,
)
from services.api.app.main import app


def test_series_contract_rejects_advance_notice_and_accepts_supported_recurrence() -> None:
    schema = app.openapi()["components"]["schemas"]["SeriesCreateRequest"]
    assert schema["additionalProperties"] is False
    frequency_schema = app.openapi()["components"]["schemas"]["ReminderFrequency"]
    assert frequency_schema["enum"] == [
        "none",
        "daily",
        "weekly",
        "monthly",
        "yearly",
    ]
    assert "advance_notice_days" not in schema["properties"]
    payload = {
        "reminder_type": "medication",
        "title": "每月預防藥",
        "first_execution_at": "2026-08-20T09:00:00+08:00",
        "frequency": "monthly",
        "interval": 3,
    }
    assert SeriesCreateRequest.model_validate(payload).interval == 3
    try:
        SeriesCreateRequest.model_validate({**payload, "advance_notice_days": 2})
    except ValueError:
        pass
    else:
        raise AssertionError("不應接受提前提醒欄位")


def test_series_stop_and_occurrence_edit_scope_are_explicit() -> None:
    assert SeriesStopRequest.model_validate({"expected_version": 1, "reason": "調整"})
    assert OccurrenceEditRequest.model_validate(
        {"scope": "this_and_future", "expected_version": 0, "reason": "調整"}
    )
    assert OccurrenceActionRequest.model_validate({"action": "completed", "expected_version": 0})
