from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.authentication.session_service import SessionService
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


class FakeAuthRepository:
    def __init__(self, user: User) -> None:
        self.user = user
        self.sessions = {}
        self.refresh = {}
        self.values = []
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
        self.binding = LineUserBinding(
            id=uuid4(), line_user_id="line-user", user_id=user.id, status="active"
        )

    async def find_user_by_username(self, username):
        return self.user if username == self.user.username else None

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

    async def memberships(self, user_id, active_only=False):
        if user_id != self.user.id or (active_only and self.membership.status != "active"):
            return []
        return [self.membership]

    async def get_line_binding(self, line_user_id):
        return self.binding if line_user_id == self.binding.line_user_id else None

    async def get_organization(self, organization_id):
        return self.organization if organization_id == self.organization.id else None

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
    second = await service.refresh(refresh_token=first["refresh_token"])
    assert first["refresh_token"] != second["refresh_token"]

    with pytest.raises(DomainError, match="Refresh Token 無效"):
        await service.refresh(refresh_token=first["refresh_token"])
    assert all(record.status == "revoked" for record in repository.refresh.values())


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
async def test_liff_exchange_requires_valid_binding_and_unique_active_context() -> None:
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
    )

    issued = await service.exchange_line_identity(id_token="valid-id-token")
    assert issued["user_id"] == user.id
    sessions = [value for value in repository.values if isinstance(value, SessionRecord)]
    assert sessions[-1].active_organization_id == repository.organization.id

    with pytest.raises(DomainError, match="請先完成 LINE 身分綁定"):
        await service.exchange_line_identity(id_token="invalid")
