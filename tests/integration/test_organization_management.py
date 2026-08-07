from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.organization_management import OrganizationManagementService
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.models.identity import Organization, User


class _Repository:
    def __init__(self):
        self.organization = Organization(id=uuid4(), code="ORG-US0", name="US0", status="active")
        self.user_record = User(id=uuid4(), username="staff", display_name="Staff", status="active")
        self.memberships = []

    async def get(self, organization_id):
        return self.organization if organization_id == self.organization.id else None

    async def user(self, user_id):
        return self.user_record if user_id == self.user_record.id else None

    async def membership(self, user_id, organization_id):
        return next(
            (
                m
                for m in self.memberships
                if m.user_id == user_id and m.organization_id == organization_id
            ),
            None,
        )

    async def add(self, value):
        if getattr(value, "id", None) is None:
            value.id = uuid4()
        self.memberships.append(value)
        return value


@pytest.mark.asyncio
async def test_shelter_admin_can_create_staff_or_volunteer_membership():
    repository = _Repository()
    service = OrganizationManagementService(repository, Argon2PasswordHasher())
    membership = await service.create_membership(
        organization_id=repository.organization.id,
        user_id=repository.user_record.id,
        role="VOLUNTEER",
    )
    assert membership.organization_id == repository.organization.id
    assert membership.role == "VOLUNTEER"


@pytest.mark.asyncio
async def test_pending_shelter_cannot_create_general_membership():
    repository = _Repository()
    repository.organization.status = "pending_setup"
    service = OrganizationManagementService(repository, Argon2PasswordHasher())

    with pytest.raises(DomainError, match="尚未啟用"):
        await service.create_membership(
            organization_id=repository.organization.id,
            user_id=repository.user_record.id,
            role="STAFF",
        )
