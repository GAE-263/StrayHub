from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.organization_management import OrganizationManagementService
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.models.identity import Organization, OrganizationMembership, User


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

    async def count_active_shelter_admins(self, organization_id, *, exclude_membership_id=None):
        return sum(
            1
            for membership in self.memberships
            if membership.organization_id == organization_id
            and membership.role == "SHELTER_ADMIN"
            and membership.status == "active"
            and membership.id != exclude_membership_id
        )


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
            role="STAFF",
        )


@pytest.mark.asyncio
async def test_volunteer_membership_requires_access_approval_flow() -> None:
    repository = _Repository()
    with pytest.raises(DomainError, match="志工報名與限時授權流程"):
        await OrganizationManagementService(repository, Argon2PasswordHasher()).create_membership(
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


@pytest.mark.asyncio
async def test_membership_archive_preserves_status_and_can_restore() -> None:
    repository = _Repository()
    membership = OrganizationMembership(
        id=uuid4(),
        organization_id=repository.organization.id,
        user_id=repository.user_record.id,
        role="STAFF",
        status="disabled",
    )
    repository.memberships.append(membership)
    actor_id = uuid4()
    service = OrganizationManagementService(repository, Argon2PasswordHasher())

    await service.archive_membership(membership, actor_user_id=actor_id)

    assert membership.status == "archived"
    assert membership.archived_from_status == "disabled"
    assert membership.archived_by_user_id == actor_id
    assert membership.archived_at is not None

    await service.restore_membership(membership)

    assert membership.status == "disabled"
    assert membership.archived_from_status is None
    assert membership.archived_at is None
    assert membership.archived_by_user_id is None


@pytest.mark.asyncio
async def test_archiving_last_active_shelter_admin_is_rejected() -> None:
    repository = _Repository()
    membership = OrganizationMembership(
        id=uuid4(),
        organization_id=repository.organization.id,
        user_id=repository.user_record.id,
        role="SHELTER_ADMIN",
        status="active",
    )
    repository.memberships.append(membership)

    with pytest.raises(DomainError, match="至少需要一名"):
        await OrganizationManagementService(repository, Argon2PasswordHasher()).archive_membership(
            membership, actor_user_id=uuid4()
        )


@pytest.mark.asyncio
async def test_restoring_expired_volunteer_remains_expired() -> None:
    repository = _Repository()
    membership = OrganizationMembership(
        id=uuid4(),
        organization_id=repository.organization.id,
        user_id=repository.user_record.id,
        role="VOLUNTEER",
        status="archived",
        archived_from_status="active",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )

    await OrganizationManagementService(repository, Argon2PasswordHasher()).restore_membership(
        membership
    )

    assert membership.status == "expired"
