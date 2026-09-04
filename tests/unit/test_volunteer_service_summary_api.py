from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api import volunteer_access as api
from services.api.app.api.dependencies import RequestContext
from services.api.app.application.volunteer_service_summary import (
    VolunteerServiceSummaryResult,
)
from services.api.app.domain.volunteer_experience import VolunteerVisitStatistics


@pytest.mark.asyncio
async def test_summary_api_returns_allowlisted_aggregate(monkeypatch) -> None:
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

    class _Identities:
        def __init__(self, _session):
            pass

        async def get_organization(self, _organization_id):
            return SimpleNamespace(timezone="Asia/Taipei")

    class _Service:
        def __init__(self, access_repository, summary_repository, *, audit):
            captured["service_dependencies"] = (access_repository, summary_repository, audit)

        async def for_application(self, received_application_id, **kwargs):
            captured["application_id"] = received_application_id
            captured["kwargs"] = kwargs
            return VolunteerServiceSummaryResult(
                subject_user_id,
                VolunteerVisitStatistics(
                    current_shelter_visits=2,
                    total_strayhub_visits=8,
                    visits_last_180_days=6,
                    visits_last_90_days=4,
                    visits_last_30_days=1,
                    last_visit_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
                    active_months_last_6_months=4,
                    recent_status="consistently_active",
                ),
                True,
            )

    @asynccontextmanager
    async def _scope(**_kwargs):
        yield None

    monkeypatch.setattr(api, "VolunteerAccessRepository", _AccessRepository)
    monkeypatch.setattr(api, "VolunteerServiceSummaryRepository", _SummaryRepository)
    monkeypatch.setattr(api, "VolunteerServiceSummaryService", _Service)
    monkeypatch.setattr(api, "AuthenticationRepository", _Identities)
    monkeypatch.setattr(api, "volunteer_management_scope", _scope)
    monkeypatch.setattr(api, "AuditService", lambda session: "audit")

    response = await api.get_volunteer_application_service_summary(
        organization_id,
        application_id,
        "volunteer_service_history_review",
        RequestContext(uuid4(), organization_id, uuid4(), "SHELTER_ADMIN"),
        _Session(),
    )

    assert response.total_strayhub_visits == 8
    assert response.has_active_platform_restriction is True
    assert response.approval_blocked is True
    assert captured["application_id"] == application_id
    assert captured["kwargs"]["purpose_code"] == "volunteer_service_history_review"
    assert captured["committed"] is True
