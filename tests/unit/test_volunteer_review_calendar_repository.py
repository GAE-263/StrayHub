from datetime import date
from uuid import uuid4

import pytest
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)


class _Result:
    def all(self):
        return [(date(2026, 8, 26), 2), (date(2026, 8, 27), 1)]


class _Session:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _Result()


@pytest.mark.asyncio
async def test_review_calendar_overview_is_org_scoped_pending_sql_aggregation() -> None:
    session = _Session()
    organization_id = uuid4()
    repository = VolunteerAccessRepository(session, organization_id)  # type: ignore[arg-type]

    overview = await repository.review_calendar_overview()

    assert overview == [(date(2026, 8, 26), 2), (date(2026, 8, 27), 1)]
    sql = str(session.statement)
    assert "volunteer_application_service_dates.organization_id" in sql
    assert "volunteer_applications.organization_id" in sql
    assert "volunteer_application_service_dates.status" in sql
    assert "volunteer_applications.status" in sql
    assert "GROUP BY volunteer_application_service_dates.service_date" in sql
    assert "ORDER BY volunteer_application_service_dates.service_date" in sql
    assert "volunteer_application_profiles" not in sql


@pytest.mark.asyncio
async def test_legacy_pending_service_date_counts_uses_calendar_aggregation() -> None:
    session = _Session()
    repository = VolunteerAccessRepository(session, uuid4())  # type: ignore[arg-type]

    assert await repository.pending_service_date_counts() == [
        (date(2026, 8, 26), 2),
        (date(2026, 8, 27), 1),
    ]
