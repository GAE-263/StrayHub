from __future__ import annotations

import calendar
import uuid
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta

from services.api.app.api.errors import DomainError
from services.api.app.domain.organization_timezone import local_to_utc

OCCURRENCE_NAMESPACE = uuid.UUID("2d56f7b7-cb6b-4c32-8a35-9aa80cc8c7f0")


def validate_frequency(frequency: str, interval: int) -> None:
    if frequency not in {"none", "daily", "weekly", "monthly", "yearly"}:
        raise DomainError("invalid_recurrence", "提醒週期無效", 422)
    if interval < 1 or interval > 120:
        raise DomainError("invalid_recurrence_interval", "提醒週期間隔無效", 422)
    if frequency == "none" and interval != 1:
        raise DomainError("invalid_recurrence_interval", "單次提醒間隔必須為 1", 422)


def nth_local(anchor: date, frequency: str, interval: int, index: int) -> date:
    if index < 0:
        raise ValueError("index must be non-negative")
    validate_frequency(frequency, interval)
    if frequency == "none":
        return anchor
    if frequency == "daily":
        return anchor + timedelta(days=index * interval)
    if frequency == "weekly":
        return anchor + timedelta(days=index * interval * 7)
    if frequency == "monthly":
        month_index = anchor.month - 1 + index * interval
        year, month0 = divmod(month_index, 12)
        month = month0 + 1
        return date(
            year=anchor.year + year,
            month=month,
            day=min(anchor.day, calendar.monthrange(anchor.year + year, month)[1]),
        )
    year = anchor.year + index * interval
    return date(
        year=year,
        month=anchor.month,
        day=min(anchor.day, calendar.monthrange(year, anchor.month)[1]),
    )


def nth(anchor: date, frequency: str, interval: int, index: int) -> date:
    """Public recurrence primitive used by API and tests."""
    return nth_local(anchor, frequency, interval, index)


def last_index_on_or_before(
    anchor: date, frequency: str, interval: int, target: date
) -> int | None:
    if target < anchor:
        return None
    if frequency == "none":
        return 0
    if frequency == "daily":
        return (target - anchor).days // interval
    if frequency == "weekly":
        return (target - anchor).days // (interval * 7)
    if frequency == "monthly":
        months = (target.year - anchor.year) * 12 + target.month - anchor.month
        return max(0, months // interval)
    return max(0, (target.year - anchor.year) // interval)


def occurrence_id(lineage_id: uuid.UUID, index: int) -> uuid.UUID:
    return uuid.uuid5(OCCURRENCE_NAMESPACE, f"{lineage_id}:{index}")


def occurrence_at(
    anchor_date: date,
    anchor_time: time,
    frequency: str,
    interval: int,
    index: int,
    timezone_name: str,
) -> datetime:
    return local_to_utc(
        datetime.combine(nth_local(anchor_date, frequency, interval, index), anchor_time),
        timezone_name,
    )


def iter_range(
    anchor_date: date,
    anchor_time: time,
    frequency: str,
    interval: int,
    start: date,
    end: date,
    timezone_name: str,
) -> Iterator[tuple[int, date, datetime]]:
    if end < start:
        return
    index = 0
    while True:
        day = nth_local(anchor_date, frequency, interval, index)
        if day > end:
            return
        if day >= start:
            yield (
                index,
                day,
                occurrence_at(anchor_date, anchor_time, frequency, interval, index, timezone_name),
            )
        if frequency == "none":
            return
        index += 1
        if index > 1_000_000:
            raise DomainError("recurrence_range_too_large", "提醒週期範圍過大", 422)
