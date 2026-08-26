from datetime import datetime, timezone

import asyncpg
import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.care_reminder_service import CareReminderService
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.database.scope import set_organization_scope

from tests.integration.test_care_reminder_actions import (
    DATABASE_URL,
    _cleanup,
    _context,
    _seed_occurrence,
)


@pytest.mark.asyncio
async def test_series_service_rejects_invalid_assignee_and_inactive_animal() -> None:
    ids = await _seed_occurrence()
    try:
        async with session_factory() as session:
            await set_organization_scope(session, ids["org"])
            service = CareReminderService(session, _context(ids))
            with pytest.raises(DomainError) as invalid_assignee:
                await service.create_series(
                    ids["animal"],
                    {
                        "reminder_type": "medication",
                        "title": "無效指派",
                        "anchor_local_date": datetime.now(timezone.utc).date(),
                        "anchor_local_time": datetime.now(timezone.utc).time().replace(tzinfo=None),
                        "frequency": "none",
                        "interval": 1,
                        "assignee_membership_id": ids["org"],
                    },
                )
            assert invalid_assignee.value.status_code == 422
        connection = await asyncpg.connect(DATABASE_URL)
        try:
            await connection.execute(
                "UPDATE animals SET status='archived' WHERE id=$1", ids["animal"]
            )
        finally:
            await connection.close()
        async with session_factory() as session:
            await set_organization_scope(session, ids["org"])
            with pytest.raises(DomainError) as inactive:
                await CareReminderService(session, _context(ids)).create_series(
                    ids["animal"],
                    {
                        "reminder_type": "medication",
                        "title": "非 active 動物",
                        "anchor_local_date": datetime.now(timezone.utc).date(),
                        "anchor_local_time": datetime.now(timezone.utc).time().replace(tzinfo=None),
                        "frequency": "none",
                        "interval": 1,
                    },
                )
            assert inactive.value.status_code == 422
    finally:
        await _cleanup(ids)
