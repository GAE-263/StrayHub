"""Deterministic volunteer visit statistics and presentation status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

NEW_VOLUNTEER_MAX_VISITS = 3
RECENTLY_ACTIVE_DAYS = 30
LESS_RECENTLY_ACTIVE_DAYS = 90
EXPERIENCE_WINDOW_DAYS = 180
CONSISTENTLY_ACTIVE_MONTHS = 4
ACTIVE_MONTH_WINDOW = 6


@dataclass(frozen=True)
class VolunteerVisitRecord:
    organization_id: UUID
    service_date: date
    last_activity_at: datetime


@dataclass(frozen=True)
class VolunteerVisitStatistics:
    current_shelter_visits: int
    total_strayhub_visits: int
    visits_last_180_days: int
    visits_last_90_days: int
    visits_last_30_days: int
    last_visit_at: datetime | None
    active_months_last_6_months: int
    recent_status: str


def _month_index(value: date) -> int:
    return value.year * 12 + value.month - 1


def calculate_visit_statistics(
    records: list[VolunteerVisitRecord],
    *,
    current_organization_id: UUID,
    as_of: date,
) -> VolunteerVisitStatistics:
    """Count one visit per shelter-local calendar day and membership source."""
    eligible = [record for record in records if record.service_date <= as_of]
    total = len(eligible)
    visits_30 = sum(record.service_date >= as_of - timedelta(days=29) for record in eligible)
    visits_90 = sum(record.service_date >= as_of - timedelta(days=89) for record in eligible)
    visits_180 = sum(record.service_date >= as_of - timedelta(days=179) for record in eligible)
    current = sum(record.organization_id == current_organization_id for record in eligible)
    earliest_month = _month_index(as_of) - (ACTIVE_MONTH_WINDOW - 1)
    active_months = len(
        {
            _month_index(record.service_date)
            for record in eligible
            if earliest_month <= _month_index(record.service_date) <= _month_index(as_of)
        }
    )
    if total <= NEW_VOLUNTEER_MAX_VISITS:
        recent_status = "new"
    elif active_months >= CONSISTENTLY_ACTIVE_MONTHS:
        recent_status = "consistently_active"
    elif visits_30 > 0:
        recent_status = "recently_active"
    elif visits_90 == 0:
        recent_status = "less_recently_active"
    else:
        recent_status = "active"
    return VolunteerVisitStatistics(
        current_shelter_visits=current,
        total_strayhub_visits=total,
        visits_last_180_days=visits_180,
        visits_last_90_days=visits_90,
        visits_last_30_days=visits_30,
        last_visit_at=max((record.last_activity_at for record in eligible), default=None),
        active_months_last_6_months=active_months,
        recent_status=recent_status,
    )
