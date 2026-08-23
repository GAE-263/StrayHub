from datetime import date

import pytest
from services.api.app.application.care_agenda_service import CareAgendaService
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.database.scope import set_organization_scope

from tests.integration.test_care_reminder_actions import (
    _cleanup,
    _context,
    _seed_occurrence,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_agenda_returns_mutually_exclusive_buckets_and_local_today() -> None:
    ids = await _seed_occurrence()
    try:
        async with session_factory() as session:
            await set_organization_scope(session, ids["org"])
            result = await CareAgendaService(session, _context(ids)).build(target_day=date.today())
        assert set(result["buckets"]) == {
            "today_pending",
            "overdue",
            "today_resolved",
            "next_seven_days",
        }
        ids_by_bucket = [
            item["occurrence_id"] for bucket in result["buckets"].values() for item in bucket
        ]
        assert len(ids_by_bucket) == len(set(ids_by_bucket))
        assert result["timezone"] == "Asia/Taipei"
        assert set(result["pages"]) == set(result["buckets"])
        assert result["pages"]["today_pending"]["total_count"] == result["totals"]["today_pending"]
    finally:
        await _cleanup(ids)
