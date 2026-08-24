from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_service_summary import (
    SUMMARY_PURPOSE,
    VolunteerServiceSummaryService,
    decode_summary_cursor,
    encode_summary_cursor,
)
from services.api.app.domain.tenant_context import TenantContext


class _AccessRepository:
    def __init__(self, organization_id, application, *, membership=True):
        self.organization_id = organization_id
        self.application_value = application
        self.membership = membership

    async def active_membership(self, user_id):
        return SimpleNamespace(status="active") if self.membership else None

    async def application_detail(self, application_id):
        if self.application_value is None or self.application_value.id != application_id:
            return None
        return self.application_value, []


class _SummaryRepository:
    def __init__(self):
        self.subject_user_id = None

    async def list_for_subject(self, subject_user_id, *, cursor=None, limit=50):
        self.subject_user_id = subject_user_id
        return []


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
async def test_summary_resolves_subject_from_current_application_and_audits_metadata() -> None:
    organization_id = uuid4()
    application = _application(organization_id)
    summary_repository = _SummaryRepository()
    audit = _Audit()

    page = await VolunteerServiceSummaryService(
        _AccessRepository(organization_id, application),
        summary_repository,
        audit=audit,
    ).for_application(
        application.id,
        tenant_context=TenantContext(uuid4(), organization_id, "SHELTER_ADMIN"),
        purpose_code=SUMMARY_PURPOSE,
        cursor=None,
        cursor_secret="test-secret",
        limit=50,
    )

    assert page.items == []
    assert summary_repository.subject_user_id == application.user_id
    assert audit.calls[0]["reason"] == SUMMARY_PURPOSE
    assert "items" not in audit.calls[0]
    assert "user_id" not in audit.calls[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "platform_scope"),
    (("VOLUNTEER", False), ("SHELTER_ADMIN", True), ("STAFF", False)),
)
async def test_summary_denies_non_admin_and_platform_scope(role, platform_scope) -> None:
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
            cursor=None,
            cursor_secret="test-secret",
            limit=50,
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_summary_denies_invalid_access_and_audit_failure() -> None:
    organization_id = uuid4()
    application = _application(organization_id)
    cases = [
        (
            _AccessRepository(organization_id, application),
            TenantContext(uuid4(), uuid4(), "SHELTER_ADMIN"),
            SUMMARY_PURPOSE,
            403,
        ),
        (
            _AccessRepository(organization_id, application, membership=False),
            TenantContext(uuid4(), organization_id, "SHELTER_ADMIN"),
            SUMMARY_PURPOSE,
            403,
        ),
        (
            _AccessRepository(organization_id, application),
            TenantContext(uuid4(), organization_id, "SHELTER_ADMIN"),
            "application_review",
            422,
        ),
    ]
    for repository, context, purpose, status_code in cases:
        with pytest.raises(DomainError) as error:
            await VolunteerServiceSummaryService(
                repository,
                _SummaryRepository(),
                audit=_Audit(),
            ).for_application(
                application.id,
                tenant_context=context,
                purpose_code=purpose,
                cursor=None,
                cursor_secret="test-secret",
                limit=50,
            )
        assert error.value.status_code == status_code

    with pytest.raises(DomainError) as error:
        await VolunteerServiceSummaryService(
            _AccessRepository(organization_id, application),
            _SummaryRepository(),
            audit=_Audit(fail=True),
        ).for_application(
            application.id,
            tenant_context=TenantContext(uuid4(), organization_id, "SHELTER_ADMIN"),
            purpose_code=SUMMARY_PURPOSE,
            cursor=None,
            cursor_secret="test-secret",
            limit=50,
        )
    assert error.value.status_code == 503


def test_summary_cursor_is_opaque_signed_and_bound_to_application_subject() -> None:
    application_id = uuid4()
    subject_user_id = uuid4()
    organization_id = uuid4()
    cursor = encode_summary_cursor(
        "test-secret",
        application_id=application_id,
        subject_user_id=subject_user_id,
        service_date=date(2026, 5, 20),
        organization_id=organization_id,
    )
    assert str(subject_user_id) not in cursor
    assert (
        decode_summary_cursor(
            "test-secret",
            cursor,
            application_id=application_id,
            subject_user_id=subject_user_id,
        )[1]
        == organization_id
    )
    with pytest.raises(DomainError):
        decode_summary_cursor(
            "test-secret",
            cursor,
            application_id=uuid4(),
            subject_user_id=subject_user_id,
        )
