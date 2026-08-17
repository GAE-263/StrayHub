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

    async def create_with_volunteer_policy(self, *, code, name):
        from services.api.app.persistence.models.volunteer_access import (
            OrganizationVolunteerAccessPolicy,
        )

        organization = await self.add(
            Organization(id=uuid4(), code=code, name=name, status="pending_setup")
        )
        await self.add(
            OrganizationVolunteerAccessPolicy(
                organization_id=organization.id,
                applications_enabled=True,
                default_grant_duration_hours=168,
            )
        )
        return organization


@pytest.mark.asyncio
async def test_shelter_admin_can_create_staff_membership():
    repository = _Repository()
    service = OrganizationManagementService(repository, Argon2PasswordHasher())
    membership = await service.create_membership(
        organization_id=repository.organization.id,
        user_id=repository.user_record.id,
        role="STAFF",
    )
    assert membership.organization_id == repository.organization.id
    assert membership.role == "STAFF"


@pytest.mark.asyncio
async def test_generic_membership_flow_rejects_unbounded_volunteer() -> None:
    repository = _Repository()
    service = OrganizationManagementService(repository, Argon2PasswordHasher())

    with pytest.raises(DomainError, match="志工報名與限時授權"):
        await service.create_membership(
            organization_id=repository.organization.id,
            user_id=repository.user_record.id,
            role="VOLUNTEER",
        )


@pytest.mark.asyncio
async def test_new_organization_always_creates_initial_volunteer_policy() -> None:
    repository = _Repository()
    service = OrganizationManagementService(repository, Argon2PasswordHasher())

    organization = await service.create(code="ORG-NEW", name="新收容所")

    policies = [
        value
        for value in repository.memberships
        if value.__class__.__name__ == "OrganizationVolunteerAccessPolicy"
    ]
    assert organization.code == "ORG-NEW"
    assert len(policies) == 1
    assert policies[0].organization_id == organization.id
    assert policies[0].applications_enabled is True
    assert policies[0].default_grant_duration_hours == 168


@pytest.mark.asyncio
async def test_policy_insert_failure_does_not_return_partial_organization() -> None:
    class FailingRepository(_Repository):
        async def create_with_volunteer_policy(self, *, code, name):
            original_values = list(self.memberships)
            try:
                await self.add(
                    Organization(id=uuid4(), code=code, name=name, status="pending_setup")
                )
                raise RuntimeError("policy insert failed")
            except Exception:
                self.memberships = original_values
                raise

    repository = FailingRepository()
    service = OrganizationManagementService(repository, Argon2PasswordHasher())

    with pytest.raises(RuntimeError, match="policy insert failed"):
        await service.create(code="ORG-ROLLBACK", name="回滾測試")

    assert all(value.code != "ORG-ROLLBACK" for value in repository.memberships)


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
