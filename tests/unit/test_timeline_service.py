from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.timeline_service import TimelineService


class FakeTimelineRepository:
    async def reports(self, *, animal_id, start_date, end_date):
        return [SimpleNamespace(submitted_at=datetime(2026, 8, 7, tzinfo=timezone.utc), id=uuid4())]


@pytest.mark.asyncio
async def test_recent_timeline_returns_fourteen_days_and_report_count() -> None:
    days = await TimelineService(FakeTimelineRepository()).recent(
        animal_id=uuid4(), end_date=date(2026, 8, 7)
    )

    assert len(days) == 14
    assert days[-1].report_count == 1
    assert days[0].state == "no_report"
