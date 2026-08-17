from datetime import date
from time import perf_counter

from services.api.app.domain.care_recurrence import last_index_on_or_before, nth_local
from tests.fixtures.medical_care import agenda_occurrence_plan


def test_mixed_agenda_fixture_has_exact_four_bucket_partition() -> None:
    plans = agenda_occurrence_plan(today=date(2026, 8, 16), count=500)
    ids = [str(item["occurrence_id"]) for item in plans]
    assert len(ids) == len(set(ids)) == 500
    assert {str(item["bucket"]) for item in plans} == {
        "today_pending",
        "overdue",
        "today_resolved",
        "next_seven_days",
    }


def test_long_daily_series_uses_ordinal_math_and_cursor_has_no_duplicates() -> None:
    start = date(2020, 1, 1)
    target = date(2026, 8, 16)
    last = last_index_on_or_before(start, "daily", 1, target)
    assert last is not None and last > 2000
    page_size = 100
    seen: list[int] = []
    cursor = last
    while cursor >= 0 and len(seen) < 1000:
        page = list(range(max(0, cursor - page_size + 1), cursor + 1))
        seen.extend(reversed(page))
        cursor -= page_size
    assert len(seen) == len(set(seen))
    assert nth_local(start, "daily", 1, last) <= target


def test_recurrence_projection_budget() -> None:
    started = perf_counter()
    for index in range(10_000):
        nth_local(date(2020, 1, 31), "monthly", 3, index)
    assert perf_counter() - started < 1.0
