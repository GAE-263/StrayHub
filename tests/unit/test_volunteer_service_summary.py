from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_service_summary import (
    SUMMARY_PURPOSE,
    VolunteerServiceSummaryService,
)
from services.api.app.domain.tenant_context import TenantContext


class _AccessRepository:
    def __init__(self, organization_id, application, *, membership=True):
        self.organization_id = organization_id
        self.application_value = application
        self.membership = membership

    async def active_membership(self, _user_id):
        return SimpleNamespace(status="active") if self.membership else None

    async def application_detail(self, application_id):
        if self.application_value is None or self.application_value.id != application_id:
            return None
        return self.application_value, []


class _SummaryRepository:
    def __init__(self, *, restricted=False):
        self.subject_user_id = None
        self.restricted = restricted

    async def list_visit_records(self, subject_user_id):
        self.subject_user_id = subject_user_id
        return []

    async def has_active_platform_restriction(self, subject_user_id):
        assert subject_user_id == self.subject_user_id
        return self.restricted


class _Audit:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = []

    async def record(self, **kwargs):
        if self.fail:
            from sqlalchemy.exc import SQLAlchemyError

            raise SQLAlchemyError("audit unavailable")
        self.calls.append(kwargs)


def _application(organization_id):
    return SimpleNamespace(id=uuid4(), organization_id=organization_id, user_id=uuid4())


@pytest.mark.asyncio
async def test_summary_resolves_subject_returns_only_aggregate_and_audits() -> None:
    organization_id = uuid4()
    application = _application(organization_id)
    repository = _SummaryRepository(restricted=True)
    audit = _Audit()

    result = await VolunteerServiceSummaryService(
        _AccessRepository(organization_id, application), repository, audit=audit
    ).for_application(
        application.id,
        tenant_context=TenantContext(uuid4(), organization_id, "SHELTER_ADMIN"),
        purpose_code=SUMMARY_PURPOSE,
        as_of=date(2026, 9, 3),
    )

    assert result.subject_user_id == application.user_id
    assert result.statistics.total_strayhub_visits == 0
    assert result.has_active_platform_restriction is True
    assert not hasattr(result, "items")
    assert audit.calls[0]["reason"] == SUMMARY_PURPOSE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "platform_scope"),
    (("VOLUNTEER", False), ("SHELTER_ADMIN", True), ("STAFF", False)),
)
async def test_summary_denies_non_shelter_admin(role, platform_scope) -> None:
    organization_id = uuid4()
    application = _application(organization_id)
    with pytest.raises(DomainError) as error:
        await VolunteerServiceSummaryService(
            _AccessRepository(organization_id, application),
            _SummaryRepository(),
            audit=_Audit(),
        ).for_application(
            application.id,
            tenant_context=TenantContext(
                uuid4(), organization_id, role, platform_scope=platform_scope
            ),
            purpose_code=SUMMARY_PURPOSE,
            as_of=date(2026, 9, 3),
        )
    assert error.value.status_code == 403
