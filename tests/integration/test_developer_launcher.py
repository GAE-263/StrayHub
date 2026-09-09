from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from scripts import dev
from services.api.app.api.errors import DomainError
from services.api.app.application.authentication.session_service import SessionService
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.models.identity import Organization, SessionRecord, User
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.integration.test_authentication_session import token_adapter


@pytest.mark.asyncio
async def test_platform_login_uses_runtime_rls_without_shelter_membership():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    hasher = Argon2PasswordHasher()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    user = User(
                        id=uuid4(),
                        username=f"dev-platform-{uuid4().hex}",
                        display_name="Dev test",
                        password_hash=hasher.hash("development-test-password"),
                        status="active",
                        platform_role="PLATFORM_ADMIN",
                    )
                    organization = Organization(
                        id=uuid4(), code=f"DEV-{uuid4().hex}", name="Dev Shelter", status="active"
                    )
                    session.add_all([user, organization])
                    await session.flush()
                    await session.execute(text("SET LOCAL ROLE strayhub_runtime"))
                    assert await session.scalar(text("SELECT current_user")) == "strayhub_runtime"
                    service = SessionService(
                        AuthenticationRepository(session),
                        password_hasher=hasher,
                        access_token=token_adapter(),
                    )
                    result = await service.login(
                        username=user.username, password="development-test-password"
                    )
                    assert result["platform_role"] == "PLATFORM_ADMIN"
                    assert organization.id in {org["id"] for org in result["organizations"]}
                    with pytest.raises(DomainError) as rejected:
                        await service.login(
                            username=user.username,
                            password="development-test-password",
                            public_exposure_profile="shared-demo-production",
                        )
                    assert rejected.value.status_code == 401
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_password_reset_changes_only_selected_demo_credentials_and_sessions(monkeypatch):
    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(url)
    hasher = Argon2PasswordHasher()
    names = tuple(f"dev-reset-{uuid4().hex}" for _ in range(5))
    monkeypatch.setattr(dev, "ACCOUNTS", names)
    ids = [uuid4() for _ in range(6)]
    old_hash = hasher.hash("old-development-password")
    try:
        async with AsyncSession(engine) as session, session.begin():
            for index, user_id in enumerate(ids):
                session.add(
                    User(
                        id=user_id,
                        username=names[index] if index < 5 else f"other-{uuid4().hex}",
                        display_name="Dev reset fixture",
                        password_hash=old_hash,
                        status="active",
                        platform_role="PLATFORM_ADMIN" if index == 0 else None,
                    )
                )
            await session.flush()
            for user_id in ids:
                session.add(
                    SessionRecord(
                        id=uuid4(),
                        user_id=user_id,
                        status="active",
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                    )
                )
        before = await dev.database_state(url)
        assert set(names) <= before["users"]
        # A read-only restart inspection must preserve all hashes and session states.
        async with AsyncSession(engine) as session:
            users = (await session.scalars(select(User).where(User.id.in_(ids)))).all()
            assert all(user.password_hash == old_hash for user in users)
            assert set(
                (
                    await session.scalars(
                        select(SessionRecord.status).where(SessionRecord.user_id.in_(ids))
                    )
                ).all()
            ) == {"active"}
        await dev.reset_password(url, "new-development-password")
        async with AsyncSession(engine) as session:
            users = (await session.scalars(select(User).where(User.id.in_(ids)))).all()
            for user in users:
                if user.id == ids[-1]:
                    assert user.password_hash == old_hash
                else:
                    assert hasher.verify("new-development-password", user.password_hash)
                    assert not hasher.verify("old-development-password", user.password_hash)
                assert user.status == "active"
                assert user.platform_role == ("PLATFORM_ADMIN" if user.id == ids[0] else None)
            sessions = (
                await session.scalars(select(SessionRecord).where(SessionRecord.user_id.in_(ids)))
            ).all()
            assert all(
                record.status == ("active" if record.user_id == ids[-1] else "expired")
                for record in sessions
            )
    finally:
        async with AsyncSession(engine) as session, session.begin():
            await session.execute(delete(SessionRecord).where(SessionRecord.user_id.in_(ids)))
            await session.execute(delete(User).where(User.id.in_(ids)))
        await engine.dispose()
