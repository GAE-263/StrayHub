from datetime import date
from uuid import uuid4

import pytest
from services.api.app.persistence.repositories import volunteer_service_summary_repository as module
from services.api.app.persistence.repositories.volunteer_service_summary_repository import (
    VolunteerServiceSummaryRepository,
)


class _Result:
    def all(self):
        return [
            (uuid4(), "收容所 A", date(2026, 5, 20), "recorded", 2),
            (uuid4(), "收容所 B", date(2026, 4, 15), "archived", 1),
        ]


class _Session:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _Result()


@pytest.mark.asyncio
async def test_summary_query_is_allowlisted_cross_org_aggregate(monkeypatch) -> None:
    calls = []

    async def fake_platform_scope(session):
        calls.append("platform")

    async def fake_organization_scope(session, organization_id):
        calls.append(("organization", organization_id))

    monkeypatch.setattr(module, "set_platform_scope", fake_platform_scope)
    monkeypatch.setattr(module, "set_organization_scope", fake_organization_scope)
    session = _Session()
    current_organization_id = uuid4()
    records = await VolunteerServiceSummaryRepository(
        session, current_organization_id
    ).list_for_subject(uuid4())

    assert [record.organization_name for record in records] == ["收容所 A", "收容所 B"]
    assert [record.record_count for record in records] == [2, 1]
    assert all(not hasattr(record, "applicant_name") for record in records)
    assert all(not hasattr(record, "answers") for record in records)
    assert calls == ["platform", ("organization", current_organization_id)]
    sql = str(session.statement)
    assert "care_reports.volunteer_user_id" in sql
    assert "care_reports.submitted_at" in sql
    assert "care_reports.answers" not in sql
    assert "volunteer_application_profiles" not in sql


@pytest.mark.asyncio
async def test_summary_cursor_is_subject_bound_by_service_layer_contract() -> None:
    """Repository accepts only a resolved subject; it has no user lookup API."""
    assert not hasattr(VolunteerServiceSummaryRepository, "list_for_user_id_from_request")
