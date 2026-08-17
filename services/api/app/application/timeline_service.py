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

    async def _reports(self, **kwargs):
        try:
            return await self.repository.reports(**kwargs), True
        except TypeError as error:
            # Keep lightweight legacy/fake repositories compatible while the
            # production repository accepts the organization timezone.
            if "timezone_name" not in str(error):
                raise
            kwargs.pop("timezone_name", None)
            return await self.repository.reports(**kwargs), False

    async def recent(
        self, *, animal_id: UUID, end_date: date | None = None, timezone_name: str = "UTC"
    ) -> list:
        end = end_date or date.today()
        reports, timezone_supported = await self._reports(
            animal_id=animal_id,
            start_date=end - timedelta(days=13),
            end_date=end,
            timezone_name=timezone_name,
        )
        by_date = defaultdict(list)
        from zoneinfo import ZoneInfo

        zone = ZoneInfo(timezone_name)
        for report in reports:
            by_date[
                report.submitted_at.astimezone(zone).date()
                if timezone_supported
                else report.submitted_at.date()
            ].append(report)
        return build_timeline_days(end_date=end, report_dates=by_date, days=14)

    async def date_range(
        self, *, animal_id: UUID, start_date: date, end_date: date, timezone_name: str = "UTC"
    ) -> list:
        if end_date < start_date:
            raise DomainError("invalid_date_range", "日期區間無效", 422)
        reports, timezone_supported = await self._reports(
            animal_id=animal_id,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
        )
        by_date = defaultdict(list)
        from zoneinfo import ZoneInfo

        zone = ZoneInfo(timezone_name)
        for report in reports:
            by_date[
                report.submitted_at.astimezone(zone).date()
                if timezone_supported
                else report.submitted_at.date()
            ].append(report)
        return build_timeline_days(
            end_date=end_date, report_dates=by_date, days=(end_date - start_date).days + 1
        )

    @staticmethod
    def merge_events(
        days: list,
        *,
        actual_events: list[tuple[date, dict]],
        scheduled_events: list[tuple[date, dict]],
    ) -> list:
        """Merge actual and scheduled sources while preserving report compatibility."""
        by_date = {day.date: day for day in days}
        for source, bucket_name in ((actual_events, "events"), (scheduled_events, "scheduled")):
            for day_date, event in source:
                day = by_date.get(day_date)
                if day is None:
                    continue
                bucket = getattr(day, bucket_name)
                if not any(item.get("id") == event.get("id") for item in bucket):
                    bucket.append(event)
        for day in days:
            day.events.sort(key=lambda item: (item.get("happened_at", ""), item.get("id", "")))
            day.scheduled.sort(key=lambda item: (item.get("scheduled_at", ""), item.get("id", "")))
        return days
