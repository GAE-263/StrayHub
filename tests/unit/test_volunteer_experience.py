from datetime import date, datetime, timezone
from uuid import uuid4

from services.api.app.domain.volunteer_experience import (
    VolunteerVisitRecord,
    calculate_visit_statistics,
)


def _visit(organization_id, day: date) -> VolunteerVisitRecord:
    return VolunteerVisitRecord(
        organization_id=organization_id,
        service_date=day,
        last_activity_at=datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc),
    )


def test_visit_statistics_use_inclusive_day_boundaries_and_shelter_scope() -> None:
    current, other = uuid4(), uuid4()
    as_of = date(2026, 9, 3)
    records = [
        _visit(current, date(2026, 9, 3)),
        _visit(current, date(2026, 8, 5)),  # 30-day inclusive boundary
        _visit(other, date(2026, 6, 6)),  # 90-day inclusive boundary
        _visit(other, date(2026, 3, 8)),  # 180-day inclusive boundary
        _visit(other, date(2026, 3, 7)),
        _visit(other, date(2027, 1, 1)),  # future records never count
    ]

    result = calculate_visit_statistics(records, current_organization_id=current, as_of=as_of)

    assert result.current_shelter_visits == 2
    assert result.total_strayhub_visits == 5
    assert result.visits_last_30_days == 2
    assert result.visits_last_90_days == 3
    assert result.visits_last_180_days == 4
    assert result.last_visit_at == records[0].last_activity_at


def test_visit_statistics_cover_cross_year_months_and_status_precedence() -> None:
    organization_id = uuid4()
    records = [
        _visit(organization_id, date(2025, 11, 10)),
        _visit(organization_id, date(2025, 12, 10)),
        _visit(organization_id, date(2026, 1, 10)),
        _visit(organization_id, date(2026, 2, 10)),
    ]

    result = calculate_visit_statistics(
        records,
        current_organization_id=organization_id,
        as_of=date(2026, 2, 28),
    )

    assert result.active_months_last_6_months == 4
    assert result.recent_status == "consistently_active"


def test_zero_and_single_visit_are_new() -> None:
    organization_id = uuid4()
    empty = calculate_visit_statistics(
        [], current_organization_id=organization_id, as_of=date(2026, 1, 1)
    )
    single = calculate_visit_statistics(
        [_visit(organization_id, date(2025, 12, 31))],
        current_organization_id=organization_id,
        as_of=date(2026, 1, 1),
    )

    assert empty.total_strayhub_visits == 0
    assert empty.last_visit_at is None
    assert empty.recent_status == "new"
    assert single.total_strayhub_visits == 1
    assert single.visits_last_30_days == 1
    assert single.recent_status == "new"
