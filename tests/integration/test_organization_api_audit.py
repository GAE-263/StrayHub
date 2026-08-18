import asyncio
from uuid import uuid4

import pytest
from services.api.app.api import organization_management as api
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.audit import AuditRecord
from services.api.app.persistence.models.identity import (
    Organization,
    OrganizationMembership,
    User,
)
from services.api.app.persistence.models.volunteer_access import (
    OrganizationVolunteerAccessPolicy,
)


class _Session:
    def __init__(self) -> None:
        self.values = []
        self.commit_count = 0
        self.release_callback = None

    def add(self, value):
        self.values.append(value)

    async def flush(self):
        return None

    async def commit(self):
        self.commit_count += 1
        if self.release_callback is not None:
            self.release_callback()

    async def rollback(self):
        if self.release_callback is not None:
            self.release_callback()


class _Repository:
    def __init__(self, session: _Session) -> None:
        self.session = session
        self.organization = None
        self.users = []
        self.memberships = []

    async def lock_organization(self, organization_id):
        return await self.get(organization_id)

    async def add(self, value):
        if getattr(value, "id", None) is None:
            value.id = uuid4()
        self.session.add(value)
        if isinstance(value, Organization):
            self.organization = value
        elif isinstance(value, User):
            self.users.append(value)
        elif isinstance(value, OrganizationMembership):
            self.memberships.append(value)
        return value

    async def create_with_volunteer_policy(self, *, code, name):
        organization = await self.add(Organization(code=code, name=name, status="pending_setup"))
        await self.add(
            OrganizationVolunteerAccessPolicy(
                organization_id=organization.id,
                applications_enabled=True,
                default_grant_duration_hours=168,
            )
        )
        return organization

    async def get(self, organization_id):
        if self.organization and self.organization.id == organization_id:
            return self.organization
        return None

    async def user_by_username(self, username):
        return next((user for user in self.users if user.username == username), None)

    async def membership(self, user_id, organization_id):
        return next(
            (
                membership
                for membership in self.memberships
                if membership.user_id == user_id and membership.organization_id == organization_id
            ),
            None,
        )

    async def membership_by_id(self, membership_id, organization_id):
        return next(
            (
                membership
                for membership in self.memberships
                if membership.id == membership_id and membership.organization_id == organization_id
            ),
            None,
        )

    async def volunteer_authorization_statuses(self, organization_id, membership_ids):
        return {}

    async def user(self, user_id):
        return next((user for user in self.users if user.id == user_id), None)

    async def count_active_shelter_admins(self, organization_id, *, exclude_membership_id=None):
        return sum(
            1
            for membership in self.memberships
            if membership.organization_id == organization_id
            and membership.role == "SHELTER_ADMIN"
            and membership.status == "active"
            and membership.id != exclude_membership_id
        )


class _LockedRepository(_Repository):
    def __init__(self, session: _Session, organization: Organization) -> None:
        super().__init__(session)
        self.organization = organization
        self.organization_lock = asyncio.Lock()
        session.release_callback = self.release_organization

    async def lock_organization(self, organization_id):
        await self.organization_lock.acquire()
        return await self.get(organization_id)

    def release_organization(self) -> None:
        if self.organization_lock.locked():
            self.organization_lock.release()


def _context(role: str, organization_id):
    return RequestContext(
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        role=role,
        platform_scope=role == "PLATFORM_ADMIN",
    )


@pytest.mark.asyncio
async def test_create_organization_commits_initial_admin_and_audit_atomically(monkeypatch):
    session = _Session()
    repository = _Repository(session)
    monkeypatch.setattr(api, "OrganizationRepository", lambda _session: repository)

    response = await api.create_organization(
        api.OrganizationCreateRequest(
            code="US0-API",
            name="US0 API Shelter",
            status="pending_setup",
            initial_admin_username="initial-admin",
            initial_admin_temporary_password="temporary-password",
        ),
        RequestContext(
            user_id=uuid4(),
            organization_id=None,
            membership_id=None,
            role="PLATFORM_ADMIN",
            platform_scope=True,
        ),
        session,
    )

    audits = [value for value in session.values if isinstance(value, AuditRecord)]
    assert response.status == "pending_setup"
    assert len(repository.memberships) == 1
    assert any(isinstance(value, OrganizationVolunteerAccessPolicy) for value in session.values)
    assert {audit.action for audit in audits} == {"organization.created", "membership.created"}
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_membership_update_records_before_after_audit_and_increments_version(monkeypatch):
    session = _Session()
    organization = Organization(id=uuid4(), code="US0-UPDATE", name="更新測試", status="active")
    repository = _Repository(session)
    repository.organization = organization
    target_user = User(id=uuid4(), username="staff-update", display_name="工作人員")
    membership = OrganizationMembership(
        id=uuid4(),
        organization_id=organization.id,
        user_id=target_user.id,
        role="STAFF",
        status="disabled",
        access_version=1,
    )
    repository.users.append(target_user)
    repository.memberships.append(membership)
    monkeypatch.setattr(api, "OrganizationRepository", lambda _session: repository)

    response = await api.update_membership(
        organization.id,
        membership.id,
        api.MembershipUpdateRequest(status="active", expected_access_version=1),
        _context("SHELTER_ADMIN", organization.id),
        session,
    )

    audits = [value for value in session.values if isinstance(value, AuditRecord)]
    assert response.status == "active"
    assert response.access_version == 2
    assert len(audits) == 1
    assert audits[0].result == "success"
    assert audits[0].organization_id == organization.id
    assert audits[0].before_data["status"] == "disabled"
    assert audits[0].after_data["status"] == "active"


@pytest.mark.asyncio
async def test_stale_membership_update_rolls_back_and_records_denial(monkeypatch):
    session = _Session()
    organization = Organization(id=uuid4(), code="US0-STALE", name="衝突測試", status="active")
    repository = _Repository(session)
    repository.organization = organization
    target_user = User(id=uuid4(), username="staff-stale", display_name="工作人員")
    membership = OrganizationMembership(
        id=uuid4(),
        organization_id=organization.id,
        user_id=target_user.id,
        role="STAFF",
        status="disabled",
        access_version=2,
    )
    repository.users.append(target_user)
    repository.memberships.append(membership)
    monkeypatch.setattr(api, "OrganizationRepository", lambda _session: repository)

    with pytest.raises(DomainError, match="其他操作更新"):
        await api.update_membership(
            organization.id,
            membership.id,
            api.MembershipUpdateRequest(status="active", expected_access_version=1),
            _context("SHELTER_ADMIN", organization.id),
            session,
        )

    denials = [value for value in session.values if isinstance(value, AuditRecord)]
    assert membership.status == "disabled"
    assert len(denials) == 1
    assert denials[0].result == "denied"
    assert denials[0].organization_id == organization.id
    assert denials[0].reason == "membership_state_changed"
    assert denials[0].before_data["access_version"] == 2


@pytest.mark.asyncio
async def test_concurrent_admin_archives_are_serialized_by_organization_lock(monkeypatch):
    session = _Session()
    organization = Organization(id=uuid4(), code="US0-LOCK", name="鎖定測試", status="active")
    repository = _LockedRepository(session, organization)
    memberships = [
        OrganizationMembership(
            id=uuid4(),
            organization_id=organization.id,
            user_id=uuid4(),
            role="SHELTER_ADMIN",
            status="active",
            access_version=1,
        )
        for _ in range(2)
    ]
    repository.memberships.extend(memberships)
    monkeypatch.setattr(api, "OrganizationRepository", lambda _session: repository)

    results = await asyncio.gather(
        *[
            api.archive_membership(
                organization.id,
                membership.id,
                api.MembershipMutationVersionRequest(expected_access_version=1),
                _context("SHELTER_ADMIN", organization.id),
                session,
            )
            for membership in memberships
        ],
        return_exceptions=True,
    )

    assert sum(isinstance(result, api.MembershipResponse) for result in results) == 1
    assert sum(isinstance(result, DomainError) for result in results) == 1
    assert sum(membership.status == "active" for membership in memberships) == 1
