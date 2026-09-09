from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from services.api.app.persistence.models.identity import (
    LoginAccountAbuseState,
    LoginIpAttempt,
)
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.asyncio
async def test_ip_attempt_lazy_cleanup_removes_expired_rows() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    source = "e" * 64
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    try:
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginIpAttempt).where(LoginIpAttempt.source_digest == source)
            )
        async with maker() as session, session.begin():
            session.add(
                LoginIpAttempt(
                    source_digest=source,
                    attempted_at=now - timedelta(seconds=901),
                )
            )
        async with maker() as session, session.begin():
            decision = await AuthenticationRepository(session).consume_login_ip_attempt(
                source, now=now
            )
            assert decision.allowed is True
        async with maker() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(LoginIpAttempt)
                .where(LoginIpAttempt.source_digest == source)
            )
            assert count == 1
    finally:
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginIpAttempt).where(LoginIpAttempt.source_digest == source)
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_expiry_boundary_is_inclusive_for_account_and_ip_state() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    account = "f" * 64
    source = "0" * 64
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    try:
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginAccountAbuseState).where(
                    LoginAccountAbuseState.subject_digest == account
                )
            )
            await session.execute(
                delete(LoginIpAttempt).where(LoginIpAttempt.source_digest == source)
            )
            session.add(
                LoginAccountAbuseState(
                    subject_digest=account,
                    consecutive_failures=5,
                    locked_until=now,
                    last_failed_at=now - timedelta(minutes=15),
                )
            )
            session.add(
                LoginIpAttempt(
                    source_digest=source,
                    attempted_at=now - timedelta(minutes=15),
                )
            )

        async with maker() as session, session.begin():
            repository = AuthenticationRepository(session)
            assert await repository.lock_login_account_state(account, now=now) is None
            decision = await repository.consume_login_ip_attempt(source, now=now)
            assert decision.allowed is True

        async with maker() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(LoginIpAttempt)
                .where(LoginIpAttempt.source_digest == source)
            )
            assert count == 1
    finally:
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginAccountAbuseState).where(
                    LoginAccountAbuseState.subject_digest == account
                )
            )
            await session.execute(
                delete(LoginIpAttempt).where(LoginIpAttempt.source_digest == source)
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_opportunistic_cleanup_is_bounded_to_one_hundred_rows() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    sources = [f"{index:064x}" for index in range(1, 106)]
    trigger_source = "9" * 64
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    try:
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginIpAttempt).where(
                    LoginIpAttempt.source_digest.in_([*sources, trigger_source])
                )
            )
            session.add_all(
                [
                    LoginIpAttempt(
                        source_digest=source,
                        attempted_at=now - timedelta(seconds=901),
                    )
                    for source in sources
                ]
            )

        async with maker() as session, session.begin():
            decision = await AuthenticationRepository(session).consume_login_ip_attempt(
                trigger_source, now=now
            )
            assert decision.allowed is True

        async with maker() as session:
            stale_count = await session.scalar(
                select(func.count())
                .select_from(LoginIpAttempt)
                .where(
                    LoginIpAttempt.source_digest.in_(sources),
                    LoginIpAttempt.attempted_at <= now - timedelta(minutes=15),
                )
            )
            assert stale_count == 5
    finally:
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginIpAttempt).where(
                    LoginIpAttempt.source_digest.in_([*sources, trigger_source])
                )
            )
        await engine.dispose()
