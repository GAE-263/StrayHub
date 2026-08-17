from datetime import date, datetime, time
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from services.api.app.domain.care_recurrence import (
    nth_local,
    occurrence_at,
    occurrence_id,
)
from services.api.app.domain.organization_timezone import local_day_range, local_to_utc


def test_monthly_anchor_clips_short_month_and_recovers_anchor_day() -> None:
    anchor = date(2026, 1, 31)
    assert nth_local(anchor, "monthly", 1, 1) == date(2026, 2, 28)
    assert nth_local(anchor, "monthly", 1, 2) == date(2026, 3, 31)


def test_occurrence_identity_is_stable_when_scheduled_time_changes() -> None:
    lineage = uuid4()
    assert occurrence_id(lineage, 3) == occurrence_id(lineage, 3)
    assert occurrence_id(lineage, 3) != occurrence_id(lineage, 4)
    assert isinstance(occurrence_id(lineage, 3), UUID)


def test_organization_day_is_half_open_in_local_timezone() -> None:
    start, end = local_day_range(date(2026, 8, 16), "Asia/Taipei")
    assert start == datetime.fromisoformat("2026-08-15T16:00:00+00:00")
    assert end == datetime.fromisoformat("2026-08-16T16:00:00+00:00")


def test_dst_gap_is_moved_to_first_valid_wall_clock_time() -> None:
    instant = local_to_utc(datetime(2026, 3, 8, 2, 30), "America/Los_Angeles")
    assert instant.astimezone(ZoneInfo("America/Los_Angeles")).hour == 3


def test_occurrence_at_uses_the_shelter_timezone() -> None:
    instant = occurrence_at(date(2026, 8, 16), time(9), "none", 1, 0, "Asia/Taipei")
    assert instant.isoformat() == "2026-08-16T01:00:00+00:00"
