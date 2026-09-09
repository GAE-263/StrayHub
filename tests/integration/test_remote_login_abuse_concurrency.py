from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import pytest
from services.api.app.persistence.models.identity import (
    LoginAccountAbuseState,
    LoginIpAttempt,
)
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.asyncio
async def test_concurrent_account_failures_atomically_enter_lockout() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"], pool_size=8, max_overflow=0)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    subject = "c" * 64
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    ready = asyncio.Event()
    waiting = 0
    guard = asyncio.Lock()

    async def fail_once() -> int | None:
        nonlocal waiting
        async with guard:
            waiting += 1
            if waiting == 5:
                ready.set()
        await ready.wait()
        async with maker() as session, session.begin():
            repository = AuthenticationRepository(session)
            state = await repository.lock_login_account_state(subject, now=now)
            return await repository.record_login_failure(subject, state=state, now=now)

    try:
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginAccountAbuseState).where(
                    LoginAccountAbuseState.subject_digest == subject
                )
            )
        results = await asyncio.gather(*(fail_once() for _ in range(5)))
        assert sum(result is None for result in results) == 4
        assert sum(result == 900 for result in results) == 1
    finally:
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginAccountAbuseState).where(
                    LoginAccountAbuseState.subject_digest == subject
                )
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_ip_attempts_do_not_oversell_twenty_slot_window() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"], pool_size=25, max_overflow=0)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    source = "d" * 64
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)

    async def consume():
        async with maker() as session, session.begin():
            return await AuthenticationRepository(session).consume_login_ip_attempt(source, now=now)

    try:
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginIpAttempt).where(LoginIpAttempt.source_digest == source)
            )
        results = await asyncio.gather(*(consume() for _ in range(21)))
        assert sum(result.allowed for result in results) == 20
        assert sum(not result.allowed for result in results) == 1
    finally:
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginIpAttempt).where(LoginIpAttempt.source_digest == source)
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_request_cannot_bypass_fifth_failure_lock() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"], pool_size=2, max_overflow=0)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    subject = "2" * 64
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    lock_written = asyncio.Event()
    observer_started = asyncio.Event()
    allow_commit = asyncio.Event()

    async def fifth_failure() -> int | None:
        async with maker() as session, session.begin():
            repository = AuthenticationRepository(session)
            state = await repository.lock_login_account_state(subject, now=now)
            result = await repository.record_login_failure(subject, state=state, now=now)
            lock_written.set()
            await allow_commit.wait()
            return result

    async def observe_account() -> int | None:
        await lock_written.wait()
        async with maker() as session, session.begin():
            repository = AuthenticationRepository(session)
            observer_started.set()
            state = await repository.lock_login_account_state(subject, now=now)
            return repository.account_retry_after(state, now=now)

    try:
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginAccountAbuseState).where(
                    LoginAccountAbuseState.subject_digest == subject
                )
            )
            repository = AuthenticationRepository(session)
            for _ in range(4):
                state = await repository.lock_login_account_state(subject, now=now)
                await repository.record_login_failure(subject, state=state, now=now)

        failure_task = asyncio.create_task(fifth_failure())
        observer_task = asyncio.create_task(observe_account())
        await observer_started.wait()
        allow_commit.set()

        assert await failure_task == 900
        assert await observer_task == 900
    finally:
        allow_commit.set()
        async with maker() as session, session.begin():
            await session.execute(
                delete(LoginAccountAbuseState).where(
                    LoginAccountAbuseState.subject_digest == subject
                )
            )
        await engine.dispose()
