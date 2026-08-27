from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.domain.volunteer_access import (
    DEFAULT_GRANT_DURATION_HOURS,
    effective_grant_duration_hours,
    grant_period_for_service_date,
    normalize_reason,
    request_fingerprint,
    snapshot_policy,
    validate_grant_period,
    validate_service_date_selection,
)

NOW = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)


def test_grant_period_uses_half_open_utc_interval_and_finite_expiry() -> None:
    valid_from, expires_at = validate_grant_period(NOW, NOW + timedelta(hours=168))
    assert valid_from == NOW
    assert expires_at == NOW + timedelta(hours=168)

    with pytest.raises(DomainError, match="晚於開始時間"):
        validate_grant_period(NOW, NOW)
    with pytest.raises(DomainError, match="UTC"):
        validate_grant_period(NOW.replace(tzinfo=None), NOW)


@pytest.mark.parametrize(
    ("duration_hours", "expected_expiry"),
    [
        (168, datetime(2026, 9, 16, 16, 0, tzinfo=timezone.utc)),
        (336, datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc)),
    ],
)
def test_grant_period_starts_at_taiwan_service_date_and_uses_policy_duration(
    duration_hours: int, expected_expiry: datetime
) -> None:
    valid_from, expires_at = grant_period_for_service_date(
        date(2026, 9, 10),
        timezone_name="Asia/Taipei",
        duration_hours=duration_hours,
    )

    assert valid_from == datetime(2026, 9, 9, 16, 0, tzinfo=timezone.utc)
    assert expires_at == expected_expiry


def test_effective_policy_duration_defaults_to_seven_days_but_preserves_explicit_value() -> None:
    assert effective_grant_duration_hours(SimpleNamespace()) == DEFAULT_GRANT_DURATION_HOURS == 168
    assert effective_grant_duration_hours(SimpleNamespace(default_grant_duration_hours=336)) == 336


def test_immediate_expiry_requires_explicit_confirmation() -> None:
    with pytest.raises(DomainError, match="確認立即失效"):
        validate_grant_period(
            NOW - timedelta(hours=2),
            NOW - timedelta(minutes=1),
            now=NOW,
            confirm_immediate_expiry=False,
        )
    assert validate_grant_period(
        NOW - timedelta(hours=2),
        NOW - timedelta(minutes=1),
        now=NOW,
        confirm_immediate_expiry=True,
    )


def test_policy_snapshot_and_reason_normalization_are_stable() -> None:
    assert snapshot_policy(version=3, duration_hours=168) == {
        "policy_version_used": 3,
        "duration_hours_used": 168,
    }
    with pytest.raises(DomainError, match="大於 0"):
        snapshot_policy(version=1, duration_hours=0)
    assert normalize_reason("  現場安排調整  ", required=True) == "現場安排調整"
    with pytest.raises(DomainError, match="原因"):
        normalize_reason("   ", required=True)


def test_request_fingerprint_ignores_mapping_order_but_not_payload_changes() -> None:
    operation_id = uuid4()
    left = request_fingerprint({"operation_id": operation_id, "items": [2, 1]})
    right = request_fingerprint({"items": [2, 1], "operation_id": operation_id})
    changed = request_fingerprint({"items": [1, 2], "operation_id": operation_id})
    assert left == right
    assert left != changed


def test_service_date_selection_accepts_unique_dates_within_next_two_weeks() -> None:
    selected = validate_service_date_selection(
        [NOW.date(), NOW.date() + timedelta(days=13)],
        today=NOW.date(),
    )
    assert selected == [NOW.date(), NOW.date() + timedelta(days=13)]


def test_service_date_selection_rejects_dates_outside_next_two_weeks_and_duplicates() -> None:
    with pytest.raises(DomainError, match="兩週"):
        validate_service_date_selection(
            [NOW.date() + timedelta(days=14)],
            today=NOW.date(),
        )
    with pytest.raises(DomainError, match="重複"):
        validate_service_date_selection(
            [NOW.date(), NOW.date()],
            today=NOW.date(),
        )
