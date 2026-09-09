from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from services.api.app.persistence.repositories import volunteer_service_summary_repository as module
from services.api.app.persistence.repositories.volunteer_service_summary_repository import (
    VolunteerServiceSummaryRepository,
)


class _Result:
    def all(self):
        return [(uuid4(), date(2026, 5, 20), datetime(2026, 5, 20, tzinfo=timezone.utc))]


class _Session:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _Result()


@pytest.mark.asyncio
async def test_visit_query_is_cross_org_but_returns_no_shelter_metadata(monkeypatch) -> None:
    calls = []

    async def fake_platform_scope(_session):
        calls.append("platform")

    async def fake_organization_scope(_session, organization_id):
        calls.append(("organization", organization_id))

    monkeypatch.setattr(module, "set_platform_scope", fake_platform_scope)
    monkeypatch.setattr(module, "set_organization_scope", fake_organization_scope)
    session = _Session()
    current_organization_id = uuid4()
    records = await VolunteerServiceSummaryRepository(
        session, current_organization_id
    ).list_visit_records(uuid4())

    assert len(records) == 1
    assert not hasattr(records[0], "organization_name")
    assert calls == ["platform", ("organization", current_organization_id)]
    sql = str(session.statement)
    assert "care_reports.volunteer_user_id" in sql
    assert "GROUP BY care_reports.organization_id" in sql
    assert "organizations.name" not in sql
    assert "care_reports.answers" not in sql
