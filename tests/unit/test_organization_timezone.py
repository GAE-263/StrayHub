from datetime import date, datetime, timezone

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.domain.organization_timezone import (
    assert_timezone_version,
    local_day_range,
    local_to_utc,
    validate_timezone,
)


def test_taipei_local_day_is_utc_half_open_range() -> None:
    start, end = local_day_range(date(2026, 8, 16), "Asia/Taipei")
    assert start == datetime(2026, 8, 15, 16, tzinfo=timezone.utc)
    assert end == datetime(2026, 8, 16, 16, tzinfo=timezone.utc)


def test_dst_gap_moves_to_first_valid_instant_and_fold_uses_first_occurrence() -> None:
    assert local_to_utc(datetime(2026, 3, 8, 2, 30), "America/New_York") == datetime(
        2026, 3, 8, 7, 0, tzinfo=timezone.utc
    )
    assert local_to_utc(datetime(2026, 11, 1, 1, 30), "America/New_York") == datetime(
        2026, 11, 1, 5, 30, tzinfo=timezone.utc
    )


def test_invalid_timezone_and_stale_version_are_rejected() -> None:
    with pytest.raises(DomainError, match="時區格式無效"):
        validate_timezone("Mars/Shelter")
    with pytest.raises(DomainError, match="時區已變更"):
        assert_timezone_version(1, 2)
