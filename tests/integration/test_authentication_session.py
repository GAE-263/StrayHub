from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.authentication.session_service import SessionService
from services.api.app.application.ports.authentication import ActiveVolunteerEntryReference
from services.api.app.infrastructure.auth.access_token_adapter import JwtAccessTokenAdapter
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.models.identity import (
    LineUserBinding,
    Organization,
    OrganizationMembership,
    RefreshTokenRecord,
    SessionRecord,
    User,
)
from services.api.app.persistence.models.volunteer_access import VolunteerAccessGrant


class FakeAuthRepository:
    def __init__(self, user: User) -> None:
        self.user = user
        self.sessions = {}
        self.refresh = {}
        self.values = []
        self.platform_scope_enabled = False
        self.organization = Organization(
            id=uuid4(), name="Shelter", code="SHELTER", status="active"
        )
        self.membership = OrganizationMembership(
            id=uuid4(),
            organization_id=self.organization.id,
            user_id=user.id,
            role="VOLUNTEER",
            status="active",
        )
        self.grants: list[VolunteerAccessGrant] = []
        self.binding = LineUserBinding(
            id=uuid4(), line_user_id="line-user", user_id=user.id, status="active"
        )

    async def find_user_by_username(self, username):
        return self.user if username == self.user.username else None

    async def set_authentication_user_scope(self, _user_id):
        return None

    async def set_authentication_context_scope(self, _user_id, _organization_id):
        return None

    async def set_platform_scope(self):
        self.platform_scope_enabled = True

    async def add(self, value):
        if getattr(value, "id", None) is None:
            value.id = uuid4()
        self.values.append(value)
        if isinstance(value, SessionRecord):
            self.sessions[value.id] = value
        if isinstance(value, RefreshTokenRecord):
            self.refresh[value.token_digest] = value
        return value

    async def get_refresh_token(self, digest):
        return self.refresh.get(digest)

    async def get_session(self, session_id):
        return self.sessions.get(session_id)

    async def get_user(self, user_id):
        return self.user if user_id == self.user.id else None

    async def lock_user(self, user_id):
        return self.user if user_id == self.user.id else None

    async def memberships(self, user_id, active_only=False):
        if user_id != self.user.id or (active_only and self.membership.status != "active"):
            return []
        return [self.membership]

    async def effective_organization_access(self, user_id):
        return [
            (membership, self.organization)
            for membership in await self.memberships(user_id, active_only=True)
            if self.organization.status == "active"
        ]

    async def access_grants_for_memberships(self, user_id, membership_ids):
        return [
            grant
            for grant in self.grants
            if grant.user_id == user_id and grant.membership_id in membership_ids
        ]

    async def get_line_binding(self, line_user_id):
        return self.binding if line_user_id == self.binding.line_user_id else None

    async def lock_line_binding(self, line_user_id):
        return await self.get_line_binding(line_user_id)

    async def get_organization(self, organization_id):
        return self.organization if organization_id == self.organization.id else None

    async def lock_effective_volunteer_access(self, user_id, organization_id):
        if (
            self.membership is not None
            and self.membership.user_id == user_id
            and self.membership.organization_id == organization_id
            and self.membership.role == "VOLUNTEER"
            and self.membership.status == "active"
        ):
            return self.membership, object()
        return None

    async def get_membership(self, user_id, organization_id):
        if (
            self.membership is not None
            and self.membership.user_id == user_id
            and self.membership.organization_id == organization_id
        ):
            return self.membership
        return None

    async def latest_volunteer_application(self, user_id, organization_id):
        return None

    async def organizations(self, *, active_only=False):
        if self.user.platform_role == "PLATFORM_ADMIN" and not self.platform_scope_enabled:
            return []
        return (
            [self.organization] if not active_only or self.organization.status == "active" else []
        )

    async def revoke_refresh_family(self, family_id):
        for record in self.refresh.values():
            if record.family_id == family_id:
                record.status = "revoked"

    async def refresh_tokens_for_session(self, session_id):
        return [record for record in self.refresh.values() if record.session_id == session_id]


def token_adapter() -> JwtAccessTokenAdapter:
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    public = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
    return JwtAccessTokenAdapter(
        private_key=private,
        public_keys={"active": public},
        issuer="test",
        audience="api",
    )


class FakeLineVerifier:
    async def verify(self, token: str) -> str:
        return "line-user" if token == "valid-id-token" else "unknown-line-user"


class FakeEntryResolver:
    def __init__(self, organization_id):
        self.organization_id = organization_id

    async def resolve(self, raw_reference):
        if raw_reference != "valid-entry":
            return None
        return ActiveVolunteerEntryReference(uuid4(), self.organization_id, "SHELTER", "Shelter")


@pytest.mark.asyncio
async def test_current_user_exposes_membership_and_matching_grant_validity() -> None:
    user = User(id=uuid4(), username="volunteer", display_name="Volunteer", status="active")
    repository = FakeAuthRepository(user)
    now = datetime.now(timezone.utc)
    repository.membership.valid_from = now - timedelta(hours=1)
    repository.membership.expires_at = now + timedelta(hours=1)
    repository.grants.append(
        VolunteerAccessGrant(
            id=uuid4(),
            organization_id=repository.organization.id,
            user_id=user.id,
            membership_id=repository.membership.id,
            application_id=uuid4(),
            status="active",
            valid_from=now - timedelta(hours=1),
            expires_at=now + timedelta(hours=1),
        )
    )
    session = SessionRecord(
        id=uuid4(),
        user_id=user.id,
        status="active",
        expires_at=now + timedelta(hours=1),
    )
    repository.sessions[session.id] = session
    service = SessionService(
        repository, password_hasher=Argon2PasswordHasher(), access_token=token_adapter()
    )

    result = await service.current_user(session_id=session.id)

    membership = result["memberships"][0]
    assert membership["valid_from"] == repository.membership.valid_from
    assert membership["expires_at"] == repository.membership.expires_at
    assert membership["access_grant"]["membership_id"] == repository.membership.id
    assert membership["access_grant"]["organization_id"] == repository.organization.id
    assert membership["access_grant"]["status"] == "active"


@pytest.mark.asyncio
async def test_current_user_does_not_attach_grant_from_another_organization() -> None:
    user = User(id=uuid4(), username="volunteer", display_name="Volunteer", status="active")
    repository = FakeAuthRepository(user)
    now = datetime.now(timezone.utc)
    repository.grants.append(
        VolunteerAccessGrant(
            id=uuid4(),
            organization_id=uuid4(),
            user_id=user.id,
            membership_id=repository.membership.id,
            application_id=uuid4(),
            status="active",
            valid_from=now - timedelta(hours=1),
            expires_at=now + timedelta(hours=1),
        )
    )
    session = SessionRecord(
        id=uuid4(),
        user_id=user.id,
        status="active",
        expires_at=now + timedelta(hours=1),
    )
    repository.sessions[session.id] = session
    service = SessionService(
        repository, password_hasher=Argon2PasswordHasher(), access_token=token_adapter()
    )

    result = await service.current_user(session_id=session.id)

    assert result["memberships"][0]["access_grant"] is None


@pytest.mark.asyncio
async def test_login_refresh_rotation_and_family_replay() -> None:
    hasher = Argon2PasswordHasher()
    user = User(
        id=uuid4(),
        username="staff",
        display_name="Staff",
        password_hash=hasher.hash("password"),
        status="active",
    )
    repository = FakeAuthRepository(user)
    service = SessionService(
        repository,
        password_hasher=hasher,
        access_token=token_adapter(),
        refresh_ttl_seconds=3600,
    )

    first = await service.login(username="staff", password="password")
    assert first["organizations"][0]["code"] == "SHELTER"
    second = await service.refresh(refresh_token=first["refresh_token"])
    assert first["refresh_token"] != second["refresh_token"]

    with pytest.raises(DomainError, match="Refresh Token 無效"):
        await service.refresh(refresh_token=first["refresh_token"])
    assert all(record.status == "revoked" for record in repository.refresh.values())


@pytest.mark.asyncio
async def test_platform_admin_login_lists_active_organizations_without_membership() -> None:
    hasher = Argon2PasswordHasher()
    user = User(
        id=uuid4(),
        username="platform-admin",
        display_name="Platform Admin",
        password_hash=hasher.hash("password"),
        platform_role="PLATFORM_ADMIN",
        status="active",
    )
    repository = FakeAuthRepository(user)
    repository.membership = None
    service = SessionService(repository, password_hasher=hasher, access_token=token_adapter())

    result = await service.login(username="platform-admin", password="password")

    assert repository.platform_scope_enabled is True
    assert result["platform_role"] == "PLATFORM_ADMIN"
    assert result["organizations"] == [
        {
            "id": repository.organization.id,
            "code": "SHELTER",
            "name": "Shelter",
            "role": "PLATFORM_ADMIN",
        }
    ]


@pytest.mark.asyncio
async def test_logout_revokes_session_refresh_tokens() -> None:
    hasher = Argon2PasswordHasher()
    user = User(
        id=uuid4(),
        username="staff",
        display_name="Staff",
        password_hash=hasher.hash("password"),
        status="active",
    )
    repository = FakeAuthRepository(user)
    service = SessionService(repository, password_hasher=hasher, access_token=token_adapter())

    issued = await service.login(username="staff", password="password")
    await service.logout(session_id=issued["session_id"])

    assert repository.sessions[issued["session_id"]].status == "revoked"
    assert all(record.status == "revoked" for record in repository.refresh.values())


@pytest.mark.asyncio
async def test_login_rejects_disabled_membership_or_suspended_shelter() -> None:
    hasher = Argon2PasswordHasher()
    user = User(
        id=uuid4(),
        username="disabled-staff",
        display_name="Disabled Staff",
        password_hash=hasher.hash("password"),
        status="active",
    )
    repository = FakeAuthRepository(user)
    service = SessionService(repository, password_hasher=hasher, access_token=token_adapter())

    repository.membership.status = "disabled"
    with pytest.raises(DomainError, match="帳號或密碼錯誤"):
        await service.login(username=user.username, password="password")

    repository.membership.status = "active"
    repository.organization.status = "suspended"
    with pytest.raises(DomainError, match="帳號或密碼錯誤"):
        await service.login(username=user.username, password="password")


@pytest.mark.asyncio
async def test_liff_exchange_requires_valid_binding_and_entry_context() -> None:
    hasher = Argon2PasswordHasher()
    user = User(
        id=uuid4(),
        username="volunteer",
        display_name="Volunteer",
        status="active",
    )
    repository = FakeAuthRepository(user)
    service = SessionService(
        repository,
        password_hasher=hasher,
        access_token=token_adapter(),
        line_verifier=FakeLineVerifier(),
        entry_resolver=FakeEntryResolver(repository.organization.id),
    )

    issued = await service.exchange_line_identity(
        id_token="valid-id-token", shelter_entry_reference="valid-entry"
    )
    assert issued["state"] == "ACTIVE"
    assert issued["user_id"] == user.id
    sessions = [value for value in repository.values if isinstance(value, SessionRecord)]
    assert sessions[-1].active_organization_id == repository.organization.id

    result = await service.exchange_line_identity(
        id_token="invalid", shelter_entry_reference="valid-entry"
    )
    assert result["state"] == "NEW"
