import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from services.api.app.application.authentication.session_service import (
    REMOTE_MANAGEMENT_ROLLBACK_REASON,
    RemoteSessionRollbackService,
    SessionService,
)
from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from services.api.app.persistence.models.identity import RefreshTokenRecord, SessionRecord, User
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.integration.test_authentication_session import token_adapter


@pytest.mark.asyncio
async def test_selective_rollback_revokes_remote_families_and_is_idempotent() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    users = {
        label: User(id=uuid4(), username=f"rollback-{label}-{uuid4()}", display_name=label)
        for label in (
            "remote-staff",
            "remote-shelter-admin",
            "local-staff",
            "local-shelter-admin",
            "local-platform-admin",
            "liff-volunteer",
            "legacy-user",
        )
    }
    users["local-platform-admin"].platform_role = "PLATFORM_ADMIN"
    session_ids = [uuid4() for _ in users]
    now = datetime.now(timezone.utc)
    try:
        async with maker() as session, session.begin():
            session.add_all(users.values())
            await session.flush()
            origins = [
                ("remote_management_demo", "shared-demo-production"),
                ("remote_management_demo", "shared-demo-dev"),
                ("local_web", None),
                ("local_web", None),
                ("local_web", None),
                ("liff", None),
                ("legacy", None),
            ]
            for session_id, user, (origin, profile) in zip(
                session_ids, users.values(), origins, strict=True
            ):
                session.add(
                    SessionRecord(
                        id=session_id,
                        user_id=user.id,
                        status="active",
                        expires_at=now + timedelta(hours=1),
                        session_origin=origin,
                        public_profile=profile,
                    )
                )
            await session.flush()
            for session_id in session_ids:
                session.add(
                    RefreshTokenRecord(
                        session_id=session_id,
                        token_digest=uuid4().hex + uuid4().hex,
                        family_id=uuid4(),
                        status="active",
                        expires_at=now + timedelta(hours=1),
                    )
                )
        async with maker() as session, session.begin():
            result = await RemoteSessionRollbackService(
                AuthenticationRepository(session)
            ).revoke_remote_management_sessions()
            assert result.reason == REMOTE_MANAGEMENT_ROLLBACK_REASON
            assert (result.sessions_revoked, result.refresh_tokens_revoked) == (2, 2)
        async with maker() as session, session.begin():
            repeated = await RemoteSessionRollbackService(
                AuthenticationRepository(session)
            ).revoke_remote_management_sessions()
            assert (repeated.sessions_revoked, repeated.refresh_tokens_revoked) == (0, 0)
        async with maker() as session:
            rows = [await session.get(SessionRecord, session_id) for session_id in session_ids]
            assert [row.status for row in rows if row is not None] == [
                "revoked",
                "revoked",
                "active",
                "active",
                "active",
                "active",
                "active",
            ]
    finally:
        async with maker() as session, session.begin():
            await session.execute(
                delete(RefreshTokenRecord).where(RefreshTokenRecord.session_id.in_(session_ids))
            )
            await session.execute(delete(SessionRecord).where(SessionRecord.id.in_(session_ids)))
            user_ids = [user.id for user in users.values()]
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await engine.dispose()


@pytest.mark.asyncio
async def test_refresh_rotation_committed_during_rollback_is_still_revoked() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid4()
    session_id = uuid4()
    old_refresh_id = uuid4()
    new_refresh_id = uuid4()
    family_id = uuid4()
    now = datetime.now(timezone.utc)
    locked = asyncio.Event()
    allow_rotation = asyncio.Event()
    rollback_started = asyncio.Event()
    try:
        async with maker() as session, session.begin():
            session.add(User(id=user_id, username=f"race-{user_id}", display_name="Race"))
            await session.flush()
            session.add(
                SessionRecord(
                    id=session_id,
                    user_id=user_id,
                    status="active",
                    expires_at=now + timedelta(hours=1),
                    session_origin="remote_management_demo",
                    public_profile="shared-demo-production",
                )
            )
            await session.flush()
            session.add(
                RefreshTokenRecord(
                    id=old_refresh_id,
                    session_id=session_id,
                    token_digest=uuid4().hex + uuid4().hex,
                    family_id=family_id,
                    status="active",
                    expires_at=now + timedelta(hours=1),
                )
            )

        async def rotate_under_session_lock() -> None:
            async with maker() as session, session.begin():
                repository = AuthenticationRepository(session)
                assert await repository.lock_session(session_id) is not None
                locked.set()
                await allow_rotation.wait()
                old = await session.get(RefreshTokenRecord, old_refresh_id)
                assert old is not None
                old.status = "rotated"
                session.add(
                    RefreshTokenRecord(
                        id=new_refresh_id,
                        session_id=session_id,
                        token_digest=uuid4().hex + uuid4().hex,
                        family_id=family_id,
                        status="active",
                        expires_at=now + timedelta(hours=1),
                    )
                )

        async def rollback() -> None:
            await locked.wait()
            rollback_started.set()
            async with maker() as session, session.begin():
                await RemoteSessionRollbackService(
                    AuthenticationRepository(session)
                ).revoke_remote_management_sessions()

        rotate_task = asyncio.create_task(rotate_under_session_lock())
        rollback_task = asyncio.create_task(rollback())
        await rollback_started.wait()
        allow_rotation.set()
        await asyncio.wait_for(asyncio.gather(rotate_task, rollback_task), timeout=5)

        async with maker() as session:
            record = await session.get(SessionRecord, session_id)
            refresh_records = [
                await session.get(RefreshTokenRecord, old_refresh_id),
                await session.get(RefreshTokenRecord, new_refresh_id),
            ]
            assert record is not None and record.status == "revoked"
            assert [item.status for item in refresh_records if item is not None] == [
                "rotated",
                "revoked",
            ]
    finally:
        async with maker() as session, session.begin():
            await session.execute(
                delete(RefreshTokenRecord).where(RefreshTokenRecord.session_id == session_id)
            )
            await session.execute(delete(SessionRecord).where(SessionRecord.id == session_id))
            await session.execute(delete(User).where(User.id == user_id))
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_logout_and_rollback_remain_idempotently_revoked() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid4()
    session_id = uuid4()
    now = datetime.now(timezone.utc)
    try:
        async with maker() as session, session.begin():
            session.add(User(id=user_id, username=f"logout-race-{user_id}", display_name="Race"))
            await session.flush()
            session.add(
                SessionRecord(
                    id=session_id,
                    user_id=user_id,
                    status="active",
                    expires_at=now + timedelta(hours=1),
                    session_origin="remote_management_demo",
                    public_profile="shared-demo-dev",
                )
            )
            await session.flush()
            session.add(
                RefreshTokenRecord(
                    session_id=session_id,
                    token_digest=uuid4().hex + uuid4().hex,
                    family_id=uuid4(),
                    status="active",
                    expires_at=now + timedelta(hours=1),
                )
            )

        async def logout() -> None:
            async with maker() as session, session.begin():
                await SessionService(
                    AuthenticationRepository(session),
                    password_hasher=Argon2PasswordHasher(),
                    access_token=token_adapter(),
                ).logout(session_id=session_id)

        async def rollback() -> None:
            async with maker() as session, session.begin():
                await RemoteSessionRollbackService(
                    AuthenticationRepository(session)
                ).revoke_remote_management_sessions()

        await asyncio.wait_for(asyncio.gather(logout(), rollback()), timeout=5)
        async with maker() as session:
            record = await session.get(SessionRecord, session_id)
            refresh_records = list(
                (
                    await session.execute(
                        RefreshTokenRecord.__table__.select().where(
                            RefreshTokenRecord.session_id == session_id
                        )
                    )
                ).mappings()
            )
            assert record is not None and record.status == "revoked"
            assert [item["status"] for item in refresh_records] == ["revoked"]
    finally:
        async with maker() as session, session.begin():
            await session.execute(
                delete(RefreshTokenRecord).where(RefreshTokenRecord.session_id == session_id)
            )
            await session.execute(delete(SessionRecord).where(SessionRecord.id == session_id))
            await session.execute(delete(User).where(User.id == user_id))
        await engine.dispose()
