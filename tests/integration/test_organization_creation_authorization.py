from uuid import uuid4

import pytest
from services.api.app.api import organization_management as api
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.audit import AuditRecord
from services.api.app.persistence.models.identity import Organization


class _Session:
    def __init__(self) -> None:
        self.values: list[object] = []
        self.commit_count = 0

    def add(self, value):
        self.values.append(value)

    async def flush(self):
        return None

    async def commit(self):
        self.commit_count += 1


class _Repository:
    def __init__(self, session: _Session, organization: Organization) -> None:
        self.session = session
        self.organization = organization
        self.created = False

    async def get(self, organization_id):
        return self.organization if organization_id == self.organization.id else None

    async def create_with_volunteer_policy(self, *, code, name):
        self.created = True
        raise AssertionError("a shelter admin must not reach organization creation")


def _context(role: str, organization_id=None) -> RequestContext:
    return RequestContext(
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4() if organization_id else None,
        role=role,
        platform_scope=role == "PLATFORM_ADMIN",
    )


@pytest.mark.asyncio
async def test_shelter_admin_cannot_create_organization_and_denial_is_audited(monkeypatch):
    session = _Session()
    current_org = uuid4()
    repository = _Repository(
        session,
        Organization(id=current_org, code="CURRENT", name="目前收容所", status="active"),
    )
    monkeypatch.setattr(api, "OrganizationRepository", lambda _session: repository)

    with pytest.raises(DomainError) as error:
        await api.create_organization(
            api.OrganizationCreateRequest(
                code="SHOULD-NOT-CREATE",
                name="不應建立",
                status="pending_setup",
                initial_admin_username="admin",
                initial_admin_temporary_password="password",
            ),
            _context("SHELTER_ADMIN", current_org),
            session,
        )

    assert error.value.status_code == 403
    assert repository.created is False
    denials = [value for value in session.values if isinstance(value, AuditRecord)]
    assert len(denials) == 1
    assert denials[0].action == "access_denied"
    assert denials[0].reason == "platform_admin_required"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_shelter_admin_can_update_current_shelter_timezone(monkeypatch):
    session = _Session()
    current_org = uuid4()
    organization = Organization(
        id=current_org,
        code="CURRENT",
        name="目前收容所",
        status="active",
        timezone="Asia/Taipei",
        timezone_version=1,
    )
    repository = _Repository(session, organization)
    monkeypatch.setattr(api, "OrganizationRepository", lambda _session: repository)

    response = await api.update_organization(
        current_org,
        api.OrganizationUpdateRequest(timezone="Asia/Tokyo"),
        _context("SHELTER_ADMIN", current_org),
        session,
    )

    assert response.timezone == "Asia/Tokyo"
    assert organization.timezone_version == 2
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_staff_cannot_update_shelter_settings(monkeypatch):
    session = _Session()
    current_org = uuid4()
    organization = Organization(
        id=current_org,
        code="CURRENT",
        name="目前收容所",
        status="active",
        timezone="Asia/Taipei",
        timezone_version=1,
    )
    repository = _Repository(session, organization)
    monkeypatch.setattr(api, "OrganizationRepository", lambda _session: repository)

    with pytest.raises(DomainError) as error:
        await api.update_organization(
            current_org,
            api.OrganizationUpdateRequest(timezone="UTC"),
            _context("STAFF", current_org),
            session,
        )

    assert error.value.status_code == 403
    assert organization.timezone == "Asia/Taipei"
    denials = [value for value in session.values if isinstance(value, AuditRecord)]
    assert denials and denials[0].reason == "organization_settings_denied"
