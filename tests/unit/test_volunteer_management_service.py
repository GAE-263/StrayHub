from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_management_service import VolunteerManagementService
from services.api.app.domain.tenant_context import TenantContext


class _Repository:
    def __init__(self):
        self.organization_id = uuid4()
        self.membership = SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            status="active",
            volunteer_no="V024",
            can_assist_new_volunteers=False,
        )
        self.incident_value = None
        self.restriction_value = None

    async def volunteer_membership(self, membership_id, *, for_update=False):
        return self.membership if membership_id == self.membership.id else None

    async def profile(self, _user_id):
        return SimpleNamespace(surname="黃")

    async def notes(self, _membership_id):
        return []

    async def incidents(self, _membership_id):
        return [] if self.incident_value is None else [self.incident_value]

    async def restrictions(self, _membership):
        return [] if self.restriction_value is None else [self.restriction_value]

    async def add_note(self, value):
        value.id = uuid4()
        value.created_at = datetime.now(timezone.utc)
        return value

    async def add_incident(self, value):
        value.id = uuid4()
        self.incident_value = value
        return value

    async def incident(self, incident_id, *, for_update=False):
        if self.incident_value is not None and self.incident_value.id == incident_id:
            return self.incident_value
        return None

    async def add_restriction(self, value):
        value.id = uuid4()
        self.restriction_value = value
        return value

    async def platform_restriction_for_update(self, restriction_id):
        if self.restriction_value is not None and self.restriction_value.id == restriction_id:
            return self.restriction_value
        return None


class _SummaryRepository:
    async def list_visit_records(self, _user_id):
        return []


class _Audit:
    def __init__(self):
        self.calls = []

    async def record(self, **kwargs):
        self.calls.append(kwargs)


def _context(repository, *, role="SHELTER_ADMIN", platform=False):
    return TenantContext(uuid4(), repository.organization_id, role, platform_scope=platform)


@pytest.mark.asyncio
async def test_optional_note_and_assist_flag_require_current_shelter_admin() -> None:
    repository = _Repository()
    service = VolunteerManagementService(repository, _SummaryRepository(), _Audit())
    context = _context(repository)

    note = await service.add_note(
        repository.membership.id,
        content=" 對怕生犬很有耐心。 ",
        context=context,
        author_membership_id=uuid4(),
    )
    membership = await service.set_assist_flag(
        repository.membership.id, value=True, context=context
    )

    assert note.content == "對怕生犬很有耐心。"
    assert membership.can_assist_new_volunteers is True
    with pytest.raises(DomainError):
        await service.add_note(
            repository.membership.id,
            content="不可寫入",
            context=_context(repository, role="STAFF"),
            author_membership_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_note_never_creates_incident_or_restriction() -> None:
    repository = _Repository()
    service = VolunteerManagementService(repository, _SummaryRepository(), _Audit())
    await service.add_note(
        repository.membership.id,
        content="今天較晚到",
        context=_context(repository),
        author_membership_id=uuid4(),
    )
    assert repository.incident_value is None
    assert repository.restriction_value is None


@pytest.mark.asyncio
async def test_incident_must_be_confirmed_before_restriction() -> None:
    repository = _Repository()
    service = VolunteerManagementService(repository, _SummaryRepository(), _Audit())
    context = _context(repository)
    now = datetime.now(timezone.utc)
    incident = await service.add_incident(
        repository.membership.id,
        incident_type="安全事件",
        severity="high",
        factual_summary="客觀事實",
        occurred_at=now,
        context=context,
        author_membership_id=uuid4(),
    )

    with pytest.raises(DomainError) as error:
        await service.request_restriction(
            incident.id,
            scope="PLATFORM",
            reason_category="safety",
            starts_at=now,
            ends_at=now + timedelta(days=30),
            context=context,
            requester_membership_id=uuid4(),
        )
    assert error.value.code == "incident_not_confirmed"

    await service.review_incident(incident.id, decision="confirm", context=context)
    restriction = await service.request_restriction(
        incident.id,
        scope="PLATFORM",
        reason_category="safety",
        starts_at=now,
        ends_at=now + timedelta(days=30),
        context=context,
        requester_membership_id=uuid4(),
    )
    assert restriction.status == "pending_review"
    assert restriction.approved_by_user_id is None


@pytest.mark.asyncio
async def test_only_platform_admin_can_activate_platform_restriction() -> None:
    repository = _Repository()
    service = VolunteerManagementService(repository, _SummaryRepository(), _Audit())
    repository.restriction_value = SimpleNamespace(
        id=uuid4(),
        organization_id=repository.organization_id,
        scope="PLATFORM",
        status="pending_review",
        approved_by_user_id=None,
        reviewed_at=None,
        decision_reason=None,
    )
    with pytest.raises(DomainError):
        await service.decide_platform_restriction(
            repository.restriction_value.id,
            decision="approve",
            reason=None,
            context=_context(repository),
        )

    platform_context = TenantContext(uuid4(), None, "PLATFORM_ADMIN", platform_scope=True)
    result = await service.decide_platform_restriction(
        repository.restriction_value.id,
        decision="approve",
        reason="完成正式審查",
        context=platform_context,
    )
    assert result.status == "active"
    assert result.approved_by_user_id == platform_context.user_id


@pytest.mark.asyncio
async def test_profile_detail_contains_aggregate_but_no_other_shelter_records() -> None:
    repository = _Repository()
    service = VolunteerManagementService(repository, _SummaryRepository(), _Audit())
    result = await service.detail(
        repository.membership.id,
        context=_context(repository),
        as_of=date(2026, 9, 3),
    )
    assert result.surname == "黃"
    assert result.statistics.total_strayhub_visits == 0
    assert not hasattr(result, "other_shelters")
