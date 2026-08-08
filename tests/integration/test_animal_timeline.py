from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.timeline_service import TimelineService


class _TimelineRepository:
    def __init__(self, reports: list[object]) -> None:
        self.all_reports = reports
        self.calls: list[tuple[date, date]] = []

    async def reports(self, *, animal_id, start_date, end_date):
        self.calls.append((start_date, end_date))
        return [
            report
            for report in self.all_reports
            if report.animal_id == animal_id
            and start_date <= report.submitted_at.date() <= end_date
        ]


def _report(animal_id, submitted_at, *, snapshots=None, note=None):
    return SimpleNamespace(
        id=uuid4(),
        animal_id=animal_id,
        submitted_at=submitted_at,
        answer_snapshots=snapshots,
        note=note,
    )


@pytest.mark.asyncio
async def test_timeline_fills_fourteen_days_keeps_same_day_reports_and_snapshots() -> None:
    animal_id = uuid4()
    reports = [
        _report(
            animal_id,
            datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc),
            snapshots={"emotion": {"code": "emotion.calm", "display_name": "平靜"}},
            note="早班心得",
        ),
        _report(
            animal_id,
            datetime(2026, 8, 8, 18, 0, tzinfo=timezone.utc),
            snapshots={"emotion": {"code": "emotion.calm", "display_name": "平靜"}},
            note="晚班心得",
        ),
        _report(animal_id, datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)),
        _report(animal_id, datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)),
    ]
    repository = _TimelineRepository(reports)

    days = await TimelineService(repository).recent(animal_id=animal_id, end_date=date(2026, 8, 8))

    assert len(days) == 14
    assert days[0].date == date(2026, 7, 26)
    assert days[-1].date == date(2026, 8, 8)
    assert days[-1].report_count == 2
    assert [report.note for report in days[-1].reports] == ["早班心得", "晚班心得"]
    assert days[-1].reports[0].answer_snapshots["emotion"]["display_name"] == "平靜"
    assert all(
        report.submitted_at.date() >= date(2026, 7, 26) for day in days for report in day.reports
    )


@pytest.mark.asyncio
async def test_timeline_date_range_returns_requested_days_and_no_report_state() -> None:
    animal_id = uuid4()
    repository = _TimelineRepository(
        [_report(animal_id, datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc))]
    )

    days = await TimelineService(repository).date_range(
        animal_id=animal_id, start_date=date(2026, 8, 1), end_date=date(2026, 8, 3)
    )

    assert [day.date for day in days] == [
        date(2026, 8, 1),
        date(2026, 8, 2),
        date(2026, 8, 3),
    ]
    assert [day.state for day in days] == ["no_report", "has_report", "no_report"]
    assert days[1].report_count == 1
    assert repository.calls == [(date(2026, 8, 1), date(2026, 8, 3))]
