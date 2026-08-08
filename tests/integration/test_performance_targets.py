from __future__ import annotations

from datetime import date, datetime, timezone
from time import perf_counter
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.line_postback_service import InMemoryBotDraft, LinePostbackService
from services.api.app.application.timeline_service import TimelineService
from services.api.app.domain.line_care_report_state import DraftState, DraftStateMachine


class _TimelineRepository:
    def __init__(self, reports: list[object]) -> None:
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


def test_standard_bot_postback_path_is_within_local_budget() -> None:
    organization_id = uuid4()
    volunteer_id = uuid4()
    service = LinePostbackService()
    service.register_draft(
        "performance-draft",
        InMemoryBotDraft(
            organization_id,
            volunteer_id,
            DraftStateMachine(DraftState.CONFIRMING_ANIMAL),
        ),
    )

    started = perf_counter()
    assert (
        service.handle(
            event_id="performance-event",
            line_user_id=str(volunteer_id),
            draft_token="performance-draft",
            action="confirm",
            organization_id=organization_id,
        )
        == "processed"
    )

    assert perf_counter() - started < 2.0


@pytest.mark.asyncio
async def test_timeline_summary_is_within_two_seconds_and_has_no_report_days() -> None:
    animal_id = uuid4()
    repository = _TimelineRepository(
        [
            SimpleNamespace(
                id=uuid4(),
                animal_id=animal_id,
                submitted_at=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                id=uuid4(),
                animal_id=animal_id,
                submitted_at=datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc),
            ),
        ]
    )

    started = perf_counter()
    days = await TimelineService(repository).recent(animal_id=animal_id, end_date=date(2026, 8, 8))
    elapsed = perf_counter() - started

    assert elapsed < 2.0
    assert repository.query_count == 1
    assert len(days) == 14
    assert days[-1].report_count == 2
    assert sum(day.report_count for day in days if not day.has_report) == 0
    assert sum(1 for day in days if not day.has_report) == 13
