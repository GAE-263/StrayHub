from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.platform_admin_management import (
    PlatformAdminManagementService,
)
from services.api.app.persistence.models.identity import User


class _Hasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, encoded_hash: str) -> bool:
        return encoded_hash == f"hashed:{password}"

    def needs_rehash(self, encoded_hash: str) -> bool:
        return False


class _Repository:
    def __init__(self, users: list[User]) -> None:
        self.users = {user.id: user for user in users}
        self.policy_value = SimpleNamespace(min_active_admins=1, max_active_admins=2)

    async def lock_policy(self):
        return self.policy_value

    async def policy(self):
        return self.policy_value

    async def active_count(self):
        return sum(
            user.status == "active" and user.platform_role == "PLATFORM_ADMIN"
            for user in self.users.values()
        )

    async def list_admins(self):
        return [user for user in self.users.values() if user.platform_role == "PLATFORM_ADMIN"]

    async def list_candidates(self):
        return [
            user
            for user in self.users.values()
            if user.status == "active"
            and user.platform_role is None
            and not getattr(user, "is_volunteer_account", False)
        ]

    async def user(self, user_id):
        return self.users.get(user_id)

    async def user_by_username(self, username):
        return next((user for user in self.users.values() if user.username == username), None)

    async def add_user(self, user):
        self.users[user.id] = user
        return user

    async def invalidate_sessions(self, user_id):
        return None

    async def is_volunteer_account(self, user_id):
        user = self.users.get(user_id)
        return getattr(user, "is_volunteer_account", False)


def _user(*, username: str, role: str | None = None, status: str = "active") -> User:
    return User(
        id=uuid4(),
        username=username,
        display_name=username,
        status=status,
        platform_role=role,
    )


@pytest.mark.asyncio
async def test_last_active_admin_cannot_be_disabled_or_demoted():
    admin = _user(username="admin", role="PLATFORM_ADMIN")
    repository = _Repository([admin])
    service = PlatformAdminManagementService(repository, _Hasher())

    with pytest.raises(DomainError) as disabled:
        await service.disable(admin.id)
    assert disabled.value.code == "last_platform_admin"

    with pytest.raises(DomainError) as demoted:
        await service.demote(admin.id)
    assert demoted.value.code == "last_platform_admin"
    assert admin.platform_role == "PLATFORM_ADMIN"


@pytest.mark.asyncio
async def test_create_and_promote_respect_two_admin_limit():
    first = _user(username="first", role="PLATFORM_ADMIN")
    second = _user(username="second")
    third = _user(username="third")
    repository = _Repository([first, second, third])
    service = PlatformAdminManagementService(repository, _Hasher())

    promoted = await service.promote(second.id)
    assert promoted.action == "platform_admin.promoted"
    assert second.platform_role == "PLATFORM_ADMIN"

    with pytest.raises(DomainError) as error:
        await service.promote(third.id)
    assert error.value.code == "platform_admin_limit_reached"
    assert third.platform_role is None


@pytest.mark.asyncio
async def test_create_hashes_temporary_password_and_rejects_duplicate_username():
    admin = _user(username="admin", role="PLATFORM_ADMIN")
    repository = _Repository([admin])
    service = PlatformAdminManagementService(repository, _Hasher())

    created = await service.create(
        username="new-admin",
        display_name="New Admin",
        temporary_password="temporary-secret",
    )
    assert created.user.password_hash == "hashed:temporary-secret"
    assert created.user.password_hash != "temporary-secret"

    with pytest.raises(DomainError) as error:
        await service.create(
            username="new-admin",
            display_name="Duplicate",
            temporary_password="another-secret",
        )
    assert error.value.code == "username_exists"


@pytest.mark.asyncio
async def test_replacement_is_atomic_when_target_is_not_eligible():
    outgoing = _user(username="outgoing", role="PLATFORM_ADMIN")
    replacement = _user(username="replacement", status="disabled")
    repository = _Repository([outgoing, replacement])
    service = PlatformAdminManagementService(repository, _Hasher())

    with pytest.raises(DomainError) as error:
        await service.replace(
            outgoing_user_id=outgoing.id,
            replacement_user_id=replacement.id,
        )
    assert error.value.code == "platform_admin_replacement_invalid"
    assert outgoing.platform_role == "PLATFORM_ADMIN"
    assert replacement.platform_role is None


@pytest.mark.asyncio
async def test_active_volunteer_cannot_be_promoted():
    admin = _user(username="admin", role="PLATFORM_ADMIN")
    volunteer = _user(username="volunteer")
    volunteer.is_volunteer_account = True
    repository = _Repository([admin, volunteer])
    service = PlatformAdminManagementService(repository, _Hasher())

    with pytest.raises(DomainError, match="志工") as error:
        await service.promote(volunteer.id)

    assert error.value.code == "account_not_eligible"
    assert volunteer.platform_role is None


@pytest.mark.asyncio
async def test_active_volunteer_cannot_be_replacement_target():
    outgoing = _user(username="outgoing", role="PLATFORM_ADMIN")
    volunteer = _user(username="volunteer")
    volunteer.is_volunteer_account = True
    repository = _Repository([outgoing, volunteer])
    service = PlatformAdminManagementService(repository, _Hasher())

    with pytest.raises(DomainError, match="志工") as error:
        await service.replace(
            outgoing_user_id=outgoing.id,
            replacement_user_id=volunteer.id,
        )

    assert error.value.code == "platform_admin_replacement_invalid"
    assert outgoing.platform_role == "PLATFORM_ADMIN"
    assert volunteer.platform_role is None
