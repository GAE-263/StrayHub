from datetime import date

from services.api.app.application.timeline_query import build_timeline_days


def test_timeline_fills_no_report_days_without_calling_them_normal() -> None:
    days = build_timeline_days(
        end_date=date(2026, 8, 7), report_dates={date(2026, 8, 7): ["report"]}, days=14
    )

    assert len(days) == 14
    assert days[-1].state == "has_report"
    assert days[0].state == "no_report"
    assert days[0].report_count == 0
