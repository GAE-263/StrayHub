from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.application.timeline_query import build_timeline_days
from services.api.app.persistence.repositories.timeline_repository import TimelineRepository


class TimelineService:
    def __init__(self, repository: TimelineRepository) -> None:
        self.repository = repository

    async def recent(self, *, animal_id: UUID, end_date: date | None = None) -> list:
        end = end_date or date.today()
        reports = await self.repository.reports(
            animal_id=animal_id, start_date=end - timedelta(days=13), end_date=end
        )
        by_date = defaultdict(list)
        for report in reports:
            by_date[report.submitted_at.date()].append(report)
        return build_timeline_days(end_date=end, report_dates=by_date, days=14)

    async def date_range(self, *, animal_id: UUID, start_date: date, end_date: date) -> list:
        if end_date < start_date:
            raise DomainError("invalid_date_range", "日期區間無效", 422)
        reports = await self.repository.reports(
            animal_id=animal_id, start_date=start_date, end_date=end_date
        )
        by_date = defaultdict(list)
        for report in reports:
            by_date[report.submitted_at.date()].append(report)
        return build_timeline_days(
            end_date=end_date, report_dates=by_date, days=(end_date - start_date).days + 1
        )
