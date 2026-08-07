from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.authentication.session_service import SessionService
from services.api.app.infrastructure.auth.access_token_adapter import JwtAccessTokenAdapter
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.models.identity import RefreshTokenRecord, SessionRecord, User


class FakeAuthRepository:
    def __init__(self, user: User) -> None:
        self.user = user
        self.sessions = {}
        self.refresh = {}
        self.values = []

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

    async def revoke_refresh_family(self, family_id):
        for record in self.refresh.values():
            if record.family_id == family_id:
                record.status = "revoked"


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
