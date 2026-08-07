from __future__ import annotations

from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.organization_management import OrganizationManagementService
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.models.identity import Organization, User


class _Repository:
    def __init__(self) -> None:
        self.organization = Organization(code="ORG-A", name="收容所 A", status="active")
        self.user_record = User(
            username="staff-a",
            display_name="工作人員 A",
            status="active",
        )
        self.memberships = []

    async def get(self, organization_id):
        return self.organization if organization_id == self.organization.id else None

    async def user(self, user_id):
        return self.user_record if user_id == self.user_record.id else None

    async def membership(self, user_id, organization_id):
        return next(
            (
                item
                for item in self.memberships
                if item.user_id == user_id and item.organization_id == organization_id
            ),
            None,
        )

    async def add(self, value):
        if getattr(value, "id", None) is None:
            value.id = uuid4()
        self.memberships.append(value)
        return value


@pytest.mark.asyncio
async def test_shelter_membership_can_be_created_once() -> None:
    repository = _Repository()
    service = OrganizationManagementService(repository, Argon2PasswordHasher())

    membership = await service.create_membership(
        organization_id=repository.organization.id,
        user_id=repository.user_record.id,
        role="STAFF",
    )

    assert membership.role == "STAFF"
    assert membership.status == "active"
    with pytest.raises(DomainError, match="已存在"):
        await service.create_membership(
            organization_id=repository.organization.id,
            user_id=repository.user_record.id,
            role="VOLUNTEER",
        )


@pytest.mark.asyncio
async def test_platform_role_set_is_explicitly_limited() -> None:
    repository = _Repository()
    with pytest.raises(DomainError, match="角色無效"):
        await OrganizationManagementService(repository, Argon2PasswordHasher()).create_membership(
            organization_id=repository.organization.id,
            user_id=repository.user_record.id,
            role="PLATFORM_ADMIN",
        )
