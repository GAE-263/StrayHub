from __future__ import annotations

from datetime import datetime, timezone

from services.api.app.application.line_staff_animal_input_service import (
    HEALTH_STATUS_LABELS,
    LineStaffAnimalInputService,
)


def test_health_status_labels_cover_frontend_config_values() -> None:
    # 對映前端 config 定義的五種健康狀態；缺一都可能讓標題失真。
    assert HEALTH_STATUS_LABELS == {
        "healthy": "健康",
        "needs_medical": "需要就醫",
        "in_treatment": "治療中",
        "neutered": "已絕育",
        "under_observation": "觀察中",
    }


def test_resolve_occurred_at_preserves_explicit_offset() -> None:
    result = LineStaffAnimalInputService._resolve_occurred_at(
        "2026-08-27T14:05:00+08:00", "Asia/Taipei"
    )
    assert result.tzinfo == timezone.utc
    # 14:05 台北 (+08:00) == 06:05 UTC
    assert result == datetime(2026, 8, 27, 6, 5, tzinfo=timezone.utc)


def test_resolve_occurred_at_assumes_org_timezone_when_naive() -> None:
    result = LineStaffAnimalInputService._resolve_occurred_at(
        "2026-08-27T14:05:00", "Asia/Taipei"
    )
    assert result == datetime(2026, 8, 27, 6, 5, tzinfo=timezone.utc)


def test_resolve_occurred_at_falls_back_to_now_on_missing_or_bad_input() -> None:
    before = datetime.now(timezone.utc)
    for value in (None, "", "not-a-timestamp"):
        result = LineStaffAnimalInputService._resolve_occurred_at(value, "Asia/Taipei")
        assert result.tzinfo == timezone.utc
        assert result >= before
