from uuid import uuid4

import pytest
from services.api.app.api import organization_management as api
from services.api.app.api.dependencies import RequestContext
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

    def add(self, value):
        self.values.append(value)

    async def flush(self):
        return None

    async def commit(self):
        self.commit_count += 1


class _Repository:
    def __init__(self, session: _Session) -> None:
        self.session = session
        self.organization = None
        self.users = []
        self.memberships = []

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
