from datetime import date

from services.api.app.application.timeline_query import build_timeline_days
from services.api.app.application.timeline_service import TimelineService


def test_timeline_merges_actual_and_scheduled_same_day_in_stable_order() -> None:
    days = build_timeline_days(end_date=date(2026, 8, 16), report_dates={}, days=1)
    TimelineService.merge_events(
        days,
        actual_events=[
            (date(2026, 8, 16), {"id": "m-2", "happened_at": "2026-08-16T10:00:00+08:00"}),
            (date(2026, 8, 16), {"id": "m-1", "happened_at": "2026-08-16T09:00:00+08:00"}),
        ],
        scheduled_events=[
            (date(2026, 8, 16), {"id": "r-1", "scheduled_at": "2026-08-16T08:00:00+08:00"})
        ],
    )
    assert [event["id"] for event in days[0].events] == ["m-1", "m-2"]
    assert [event["id"] for event in days[0].scheduled] == ["r-1"]
    assert not days[0].has_report


def test_timeline_merge_deduplicates_stable_source_id() -> None:
    days = build_timeline_days(end_date=date(2026, 8, 16), report_dates={}, days=1)
    event = {"id": "same", "happened_at": "2026-08-16T10:00:00+08:00"}
    TimelineService.merge_events(
        days,
        actual_events=[(date(2026, 8, 16), event), (date(2026, 8, 16), event)],
        scheduled_events=[],
    )
    assert len(days[0].events) == 1
