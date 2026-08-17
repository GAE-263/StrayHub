from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.api.app.api.errors import DomainError


def validate_timezone(name: str) -> str:
    value = (name or "").strip()
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise DomainError("invalid_timezone", "時區格式無效", 422) from exc
    return value


def local_to_utc(local_value: datetime, timezone_name: str) -> datetime:
    if local_value.tzinfo is not None:
        return local_value.astimezone(timezone.utc)
    zone = ZoneInfo(validate_timezone(timezone_name))
    aware = local_value.replace(tzinfo=zone, fold=0)
    # Python's zoneinfo represents a spring-forward gap using the old offset.
    # Round-trip through UTC and move forward to the first valid wall-clock time.
    roundtrip = aware.astimezone(timezone.utc).astimezone(zone)
    if roundtrip.replace(tzinfo=None) != local_value:
        probe = local_value
        for _ in range(180):
            probe += timedelta(minutes=1)
            candidate = probe.replace(tzinfo=zone, fold=0)
            if candidate.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == probe:
                aware = candidate
                break
    return aware.astimezone(timezone.utc)


def local_day_range(day: date, timezone_name: str) -> tuple[datetime, datetime]:
    start = local_to_utc(datetime.combine(day, time.min), timezone_name)
    end = local_to_utc(datetime.combine(day + timedelta(days=1), time.min), timezone_name)
    return start, end


def local_today(timezone_name: str, now: datetime | None = None) -> date:
    zone = ZoneInfo(validate_timezone(timezone_name))
    instant = now or datetime.now(timezone.utc)
    return instant.astimezone(zone).date()


def assert_timezone_version(expected: int, current: int) -> None:
    if expected != current:
        raise DomainError("timezone_version_conflict", "收容所時區已變更，請重新載入", 409)
