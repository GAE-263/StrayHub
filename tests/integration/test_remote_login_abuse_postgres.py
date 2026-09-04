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
async def test_account_failure_lock_and_success_reset_use_postgres_state() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    subject = "a" * 64
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    try:
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginAccountAbuseState).where(
                    LoginAccountAbuseState.subject_digest == subject
                )
            )
        for expected in range(1, 6):
            async with maker() as session, session.begin():
                repository = AuthenticationRepository(session)
                state = await repository.lock_login_account_state(subject, now=now)
                retry_after = await repository.record_login_failure(subject, state=state, now=now)
                assert retry_after == (900 if expected == 5 else None)

        async with maker() as session, session.begin():
            repository = AuthenticationRepository(session)
            state = await repository.lock_login_account_state(subject, now=now)
            assert state is not None and state.consecutive_failures == 5
            assert repository.account_retry_after(state, now=now) == 900

        async with maker() as session, session.begin():
            repository = AuthenticationRepository(session)
            state = await repository.lock_login_account_state(
                subject, now=now + timedelta(seconds=901)
            )
            assert state is None
            await repository.clear_login_account_state(subject)
    finally:
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginAccountAbuseState).where(
                    LoginAccountAbuseState.subject_digest == subject
                )
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_ip_window_allows_twenty_rejects_twenty_first_and_does_not_oversell() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    source = "b" * 64
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    try:
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginIpAttempt).where(LoginIpAttempt.source_digest == source)
            )
        for _ in range(20):
            async with maker() as session, session.begin():
                decision = await AuthenticationRepository(session).consume_login_ip_attempt(
                    source, now=now
                )
                assert decision.allowed is True
        async with maker() as session, session.begin():
            decision = await AuthenticationRepository(session).consume_login_ip_attempt(
                source, now=now
            )
            assert decision.allowed is False
            assert decision.retry_after == 900
        async with maker() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(LoginIpAttempt)
                    .where(LoginIpAttempt.source_digest == source)
                )
                == 20
            )
        async with maker() as session, session.begin():
            decision = await AuthenticationRepository(session).consume_login_ip_attempt(
                source, now=now + timedelta(seconds=901)
            )
            assert decision.allowed is True
    finally:
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginIpAttempt).where(LoginIpAttempt.source_digest == source)
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_account_lock_survives_repository_engine_restart() -> None:
    database_url = os.environ["DATABASE_URL"]
    subject = "1" * 64
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    first_engine = create_async_engine(database_url)
    first_maker = async_sessionmaker(first_engine, expire_on_commit=False)
    async with first_maker() as session, session.begin():
        await session.execute(
            delete(LoginAccountAbuseState).where(LoginAccountAbuseState.subject_digest == subject)
        )
        repository = AuthenticationRepository(session)
        for _ in range(4):
            state = await repository.lock_login_account_state(subject, now=now)
            assert await repository.record_login_failure(subject, state=state, now=now) is None
    await first_engine.dispose()

    second_engine = create_async_engine(database_url)
    second_maker = async_sessionmaker(second_engine, expire_on_commit=False)
    try:
        async with second_maker() as session, session.begin():
            repository = AuthenticationRepository(session)
            state = await repository.lock_login_account_state(subject, now=now)
            assert state is not None and state.consecutive_failures == 4
            assert await repository.record_login_failure(subject, state=state, now=now) == 900
    finally:
        async with second_maker() as session, session.begin():
            await session.execute(
                delete(LoginAccountAbuseState).where(
                    LoginAccountAbuseState.subject_digest == subject
                )
            )
        await second_engine.dispose()
