from contextlib import asynccontextmanager
from datetime import date
from uuid import uuid4

import pytest
from services.api.app.api import volunteer_access as api
from services.api.app.api.dependencies import RequestContext
from services.api.app.application.volunteer_service_summary import VolunteerServiceSummaryPage
from services.api.app.persistence.repositories.volunteer_service_summary_repository import (
    VolunteerServiceSummaryRecord,
)


@pytest.mark.asyncio
async def test_summary_api_derives_application_subject_and_returns_allowlisted_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    application_id = uuid4()
    subject_user_id = uuid4()
    captured = {}

    class _Session:
        async def commit(self):
            captured["committed"] = True

    class _AccessRepository:
        def __init__(self, _session, scoped_organization_id):
            assert scoped_organization_id == organization_id

    class _SummaryRepository:
        def __init__(self, _session, scoped_organization_id):
            assert scoped_organization_id == organization_id

    class _Service:
        def __init__(self, access_repository, summary_repository, *, audit):
            captured["service_dependencies"] = (
                access_repository,
                summary_repository,
                audit,
            )

        async def for_application(self, received_application_id, **kwargs):
            captured["application_id"] = received_application_id
            captured["kwargs"] = kwargs
            return VolunteerServiceSummaryPage(
                subject_user_id,
                [
                    VolunteerServiceSummaryRecord(
                        organization_id=uuid4(),
                        organization_name="收容所 B",
                        service_date=date(2026, 5, 20),
                        service_status="recorded",
                        record_count=2,
                    )
                ],
                False,
            )

    @asynccontextmanager
    async def _scope(**_kwargs):
        yield None

    monkeypatch.setattr(api, "VolunteerAccessRepository", _AccessRepository)
    monkeypatch.setattr(api, "VolunteerServiceSummaryRepository", _SummaryRepository)
    monkeypatch.setattr(api, "VolunteerServiceSummaryService", _Service)
    monkeypatch.setattr(api, "volunteer_management_scope", _scope)
    monkeypatch.setattr(api, "AuditService", lambda session: "audit")

    response = await api.get_volunteer_application_service_summary(
        organization_id,
        application_id,
        "volunteer_service_history_review",
        None,
        50,
        RequestContext(uuid4(), organization_id, uuid4(), "SHELTER_ADMIN"),
        _Session(),
    )

    assert response.items[0].organization_name == "收容所 B"
    assert response.items[0].record_count == 2
    assert response.next_cursor is None
    assert captured["application_id"] == application_id
    assert captured["kwargs"]["purpose_code"] == "volunteer_service_history_review"
    assert captured["committed"] is True
