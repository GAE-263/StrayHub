from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.timeline_service import TimelineService


class _CountingTimelineRepository:
    def __init__(self, reports):
        self.reports_data = reports
        self.query_count = 0

    async def reports(self, *, animal_id, start_date, end_date):
        self.query_count += 1
        return [
            report
            for report in self.reports_data
            if report.animal_id == animal_id
            and start_date <= report.submitted_at.date() <= end_date
        ]


@pytest.mark.asyncio
async def test_recent_timeline_uses_one_repository_query_for_all_days() -> None:
    animal_id = uuid4()
    repository = _CountingTimelineRepository(
        [
            SimpleNamespace(
                id=uuid4(),
                animal_id=animal_id,
                submitted_at=datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                id=uuid4(),
                animal_id=animal_id,
                submitted_at=datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                id=uuid4(),
                animal_id=animal_id,
                submitted_at=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
            ),
        ]
    )

    days = await TimelineService(repository).recent(animal_id=animal_id, end_date=date(2026, 8, 8))

    assert repository.query_count == 1
    assert sum(day.report_count for day in days) == 3
    assert days[-1].report_count == 2
