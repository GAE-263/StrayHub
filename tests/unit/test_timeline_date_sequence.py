from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.timeline_query import build_timeline_days
from services.api.app.application.timeline_service import TimelineService


def test_timeline_fills_no_report_days_without_calling_them_normal() -> None:
    days = build_timeline_days(
        end_date=date(2026, 8, 7), report_dates={date(2026, 8, 7): ["report"]}, days=14
    )

    assert len(days) == 14
    assert days[-1].state == "has_report"
    assert days[0].state == "no_report"
    assert days[0].report_count == 0


def test_timeline_sequence_is_ascending_and_no_report_is_not_normal() -> None:
    end_date = date(2026, 8, 7)
    days = build_timeline_days(
        end_date=end_date,
        report_dates={date(2026, 8, 5): [SimpleNamespace(id="report-1")]},
        days=5,
    )

    assert [day.date for day in days] == [
        end_date - timedelta(days=offset) for offset in range(4, -1, -1)
    ]
    assert [day.state for day in days] == [
        "no_report",
        "no_report",
        "has_report",
        "no_report",
        "no_report",
    ]
    assert days[0].report_count == 0


@pytest.mark.asyncio
async def test_timeline_groups_timezone_aware_submission_by_its_local_date() -> None:
    class TimezoneRepository:
        async def reports(self, *, animal_id, start_date, end_date):
            return [
                SimpleNamespace(
                    id=uuid4(),
                    submitted_at=datetime(2026, 8, 8, 0, 15, tzinfo=timezone(timedelta(hours=8))),
                )
            ]

    days = await TimelineService(TimezoneRepository()).recent(
        animal_id=uuid4(), end_date=date(2026, 8, 8)
    )

    assert days[-1].date == date(2026, 8, 8)
    assert days[-1].report_count == 1


def test_timeline_rejects_invalid_day_count() -> None:
    with pytest.raises(ValueError, match="between 1 and 366"):
        build_timeline_days(end_date=date(2026, 8, 8), report_dates={}, days=0)
    with pytest.raises(ValueError, match="between 1 and 366"):
        build_timeline_days(end_date=date(2026, 8, 8), report_dates={}, days=367)


@pytest.mark.asyncio
async def test_timeline_rejects_reversed_date_range() -> None:
    class EmptyRepository:
        async def reports(self, *, animal_id, start_date, end_date):
            return []

    with pytest.raises(DomainError, match="日期區間無效"):
        await TimelineService(EmptyRepository()).date_range(
            animal_id=uuid4(), start_date=date(2026, 8, 9), end_date=date(2026, 8, 8)
        )
