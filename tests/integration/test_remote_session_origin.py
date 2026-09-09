from datetime import datetime, timezone
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.authentication.session_service import SessionService
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.models.identity import SessionRecord, User

from tests.integration.test_authentication_session import FakeAuthRepository, token_adapter


def service_for(repository: FakeAuthRepository) -> SessionService:
    return SessionService(
        repository,
        password_hasher=Argon2PasswordHasher(),
        access_token=token_adapter(),
    )


@pytest.mark.asyncio
async def test_login_origin_is_server_derived_from_trusted_profile() -> None:
    hasher = Argon2PasswordHasher()
    user = User(
        id=uuid4(),
        username="staff",
        display_name="Staff",
        password_hash=hasher.hash("password"),
        status="active",
    )
    local_repository = FakeAuthRepository(user)
    local_repository.membership.role = "STAFF"
    local_service = service_for(local_repository)
    local = await local_service.login(username="staff", password="password")
    assert local_repository.sessions[local["session_id"]].session_origin == "local_web"
    assert local_repository.sessions[local["session_id"]].public_profile is None
    local_refreshed = await local_service.refresh(refresh_token=local["refresh_token"])
    assert local_repository.sessions[local_refreshed["session_id"]].session_origin == "local_web"

    remote_repository = FakeAuthRepository(user)
    remote_repository.membership.role = "STAFF"
    remote = await service_for(remote_repository).login(
        username="staff",
        password="password",
        public_exposure_profile="shared-demo-production",
    )
    session = remote_repository.sessions[remote["session_id"]]
    assert session.session_origin == "remote_management_demo"
    assert session.public_profile == "shared-demo-production"


@pytest.mark.asyncio
async def test_refresh_preserves_persisted_origin_and_rejects_profile_switch() -> None:
    hasher = Argon2PasswordHasher()
    user = User(
        id=uuid4(),
        username="staff",
        display_name="Staff",
        password_hash=hasher.hash("password"),
        status="active",
    )
    repository = FakeAuthRepository(user)
    repository.membership.role = "STAFF"
    service = service_for(repository)
    issued = await service.login(
        username="staff",
        password="password",
        public_exposure_profile="shared-demo-dev",
    )
    refreshed = await service.refresh(
        refresh_token=issued["refresh_token"],
        public_exposure_profile="shared-demo-dev",
    )
    session = repository.sessions[refreshed["session_id"]]
    assert session.session_origin == "remote_management_demo"
    assert session.public_profile == "shared-demo-dev"

    with pytest.raises(DomainError, match="Session 無效"):
        await service.refresh(
            refresh_token=refreshed["refresh_token"],
            public_exposure_profile="shared-demo-production",
        )
    assert session.status == "revoked"
    assert all(record.status == "revoked" for record in repository.refresh.values())
    with pytest.raises(DomainError, match="Session 無效"):
        await service.current_user(session_id=session.id, public_exposure_profile=None)


@pytest.mark.asyncio
async def test_remote_refresh_role_loss_revokes_session_family() -> None:
    hasher = Argon2PasswordHasher()
    user = User(
        id=uuid4(),
        username="remote-staff",
        display_name="Remote Staff",
        password_hash=hasher.hash("password"),
        status="active",
    )
    repository = FakeAuthRepository(user)
    repository.membership.role = "STAFF"
    service = service_for(repository)
    issued = await service.login(
        username=user.username,
        password="password",
        public_exposure_profile="shared-demo-production",
    )
    repository.membership.role = "VOLUNTEER"
    with pytest.raises(DomainError, match="Session 無效"):
        await service.refresh(
            refresh_token=issued["refresh_token"],
            public_exposure_profile="shared-demo-production",
        )
    assert repository.sessions[issued["session_id"]].status == "revoked"
    assert all(record.status == "revoked" for record in repository.refresh.values())


@pytest.mark.asyncio
async def test_remote_logout_revokes_session_family() -> None:
    hasher = Argon2PasswordHasher()
    user = User(
        id=uuid4(),
        username="remote-admin",
        display_name="Remote Admin",
        password_hash=hasher.hash("password"),
        status="active",
    )
    repository = FakeAuthRepository(user)
    repository.membership.role = "SHELTER_ADMIN"
    service = service_for(repository)
    issued = await service.login(
        username=user.username,
        password="password",
        public_exposure_profile="shared-demo-dev",
    )
    await service.logout(session_id=issued["session_id"])
    assert repository.sessions[issued["session_id"]].status == "revoked"
    assert all(record.status == "revoked" for record in repository.refresh.values())


@pytest.mark.asyncio
async def test_liff_exchange_marks_session_without_changing_logout() -> None:
    from tests.integration.test_authentication_session import FakeEntryResolver, FakeLineVerifier

    user = User(id=uuid4(), username="volunteer", display_name="Volunteer", status="active")
    repository = FakeAuthRepository(user)
    service = SessionService(
        repository,
        password_hasher=Argon2PasswordHasher(),
        access_token=token_adapter(),
        line_verifier=FakeLineVerifier(),
        entry_resolver=FakeEntryResolver(repository.organization.id),
    )
    issued = await service.exchange_line_identity(
        id_token="valid-id-token", shelter_entry_reference="valid-entry"
    )
    session = repository.sessions[issued["session_id"]]
    assert session.session_origin == "liff"
    assert session.public_profile is None
    await service.logout(session_id=session.id)
    assert session.status == "revoked"


def test_legacy_default_does_not_guess_remote_from_time_or_role() -> None:
    session = SessionRecord(
        user_id=uuid4(),
        status="active",
        expires_at=datetime.now(timezone.utc),
    )
    assert SessionRecord.__table__.c.session_origin.default.arg == "legacy"
    assert SessionRecord.__table__.c.session_origin.server_default is not None
    assert session.public_profile is None
