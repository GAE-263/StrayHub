from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.organization_management import OrganizationManagementService
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.models.identity import Organization, User


@pytest.mark.asyncio
async def test_suspended_shelter_rejects_new_membership():
    organization = Organization(id=uuid4(), code="SUSP", name="Suspended", status="suspended")
    user = User(id=uuid4(), username="u", display_name="U", status="active")

    class Repository:
        async def get(self, organization_id):
            return organization if organization_id == organization.id else None

        async def user(self, user_id):
            return user if user_id == user.id else None

        async def membership(self, user_id, organization_id):
            return None

        async def add(self, value):
            return value

    with pytest.raises(DomainError, match="尚未啟用"):
        await OrganizationManagementService(Repository(), Argon2PasswordHasher()).create_membership(
            organization_id=organization.id, user_id=user.id, role="STAFF"
        )


@pytest.mark.asyncio
async def test_user_disabled_status_is_rejected_before_membership_creation():
    organization = Organization(id=uuid4(), code="ACTIVE", name="Active", status="active")
    user = User(id=uuid4(), username="disabled", display_name="Disabled", status="disabled")

    class Repository:
        async def get(self, organization_id):
            return organization if organization_id == organization.id else None

        async def user(self, user_id):
            return user if user_id == user.id else None

        async def membership(self, user_id, organization_id):
            return None

        async def add(self, value):
            return value

    with pytest.raises(DomainError, match="使用者目前停用"):
        await OrganizationManagementService(Repository(), Argon2PasswordHasher()).create_membership(
            organization_id=organization.id, user_id=user.id, role="STAFF"
        )
