from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class TimelineDay:
    date: date
    has_report: bool
    report_count: int
    reports: list[object] = field(default_factory=list)
    events: list[object] = field(default_factory=list)
    scheduled: list[object] = field(default_factory=list)

    @property
    def state(self) -> str:
        return "has_report" if self.has_report else "no_report"


def build_timeline_days(
    *,
    end_date: date,
    report_dates: dict[date, list[object]],
    days: int = 14,
) -> list[TimelineDay]:
    if days < 1 or days > 366:
        raise ValueError("days must be between 1 and 366")
    start_date = end_date - timedelta(days=days - 1)
    return [
        TimelineDay(
            date=current,
            has_report=bool(report_dates.get(current)),
            report_count=len(report_dates.get(current, [])),
            reports=list(report_dates.get(current, [])),
        )
        for offset in range(days)
        for current in [start_date + timedelta(days=offset)]
    ]
